"""Evolution engine — uses Claude to rewrite strategy code."""

from __future__ import annotations

import logging

import anthropic

from finn.database import Database
from finn.evaluation.scorer import StrategyScorer
from finn.evolution.validator import StrategyValidator
from finn.evolution.rollback import RollbackManager
from finn.evaluation.backtester import Backtester
from finn.strategy.runner import StrategyRunner
from finn.strategy.base import Strategy

logger = logging.getLogger(__name__)

EVOLUTION_PROMPT = """You are Finn's evolution engine. Your job is to write a NEW Python strategy class that improves on the current one.

## Current Strategy Code (v{current_version})
```python
{current_code}
```

## Current Strategy Description
{current_description}

## Performance Report
{performance_report}

## Recent Signals the Strategy Processed
{recent_signals_summary}

## Finn's Memory (Lessons Learned)
{memory_context}

{human_guidance}

## Your Task
Write a COMPLETE, improved Python strategy that:
1. **Keeps what worked** — if win rate is good, preserve the core logic
2. **Fixes what failed** — address the specific issues in the performance report
3. **Tries something new** — introduce ONE meaningful change (new signal weighting, sector analysis, momentum detection, crypto correlation, etc.)
4. **Uses memory** — incorporate lessons from Finn's accumulated experience
5. **Implements the interface** — must subclass Strategy with analyze() and describe()

## Rules
- The code must be a single Python file
- Must contain exactly ONE class that subclasses `Strategy`
- Must implement `analyze(self, signals: list[Signal]) -> list[Pick]` and `describe(self) -> str`
- Can only import: math, statistics, datetime, collections, itertools, functools, operator, re, json, typing
- Must import from finn.strategy.base: Strategy
- Must import from finn.models.signals: Signal, SignalType
- Must import from finn.models.picks: Pick, Conviction
- Signals may include both stocks AND crypto (look for asset_type in metadata)
- describe() should explain your SPECIFIC changes and reasoning
- Keep it practical — no theoretical perfection, just measurable improvement

## Important
- Return ONLY the Python code, no markdown fences, no explanation outside the code
- The code must be syntactically valid and complete
- Include a docstring at the top explaining what changed from the previous version
"""

SOURCE_DISCOVERY_PROMPT = """You are Finn's source discovery engine. Based on recent performance and market context, suggest new data sources or signals that could improve Finn's strategy.

## Current Signal Sources
{current_sources}

## Recent Performance
{performance_report}

## Recent Memory
{memory_context}

## Your Task
Suggest 1-3 new data sources or signal types Finn should explore. For each:
1. What is the source? (specific URL, API, data type)
2. Why would it help? (what gap does it fill?)
3. How hard is it to implement? (easy/medium/hard)

Be specific and actionable. Don't suggest sources that require paid enterprise APIs.
Focus on freely available data: RSS feeds, free APIs, public datasets, etc.

Return a JSON array of suggestions:
[{{"source": "...", "reason": "...", "difficulty": "...", "url_or_endpoint": "..."}}]
"""


class EvolutionEngine:
    """Uses Claude API to evolve strategy code based on performance."""

    def __init__(
        self,
        api_key: str,
        db: Database,
        scorer: StrategyScorer,
        validator: StrategyValidator,
        backtester: Backtester,
        rollback: RollbackManager,
        runner: StrategyRunner,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.db = db
        self.scorer = scorer
        self.validator = validator
        self.backtester = backtester
        self.rollback = rollback
        self.runner = runner

    def evolve(self, current_strategy: Strategy, current_code: str, memory_context: str = "", human_guidance: str = "") -> dict:
        """Attempt to evolve the current strategy.

        Returns dict with:
            - evolved: bool (whether evolution succeeded)
            - new_code: str | None
            - new_version: int | None
            - reason: str
            - source_suggestions: list (new data sources to explore)
        """
        current_version = self.db.get_active_strategy_version()

        # Get performance feedback
        performance_report = self.scorer.generate_feedback(current_version)

        # Get recent signals summary
        recent_signals = self._get_recent_signals_summary()

        # Ask Claude to write improved strategy
        logger.info(f"Asking Claude to evolve strategy v{current_version}...")

        prompt = EVOLUTION_PROMPT.format(
            current_version=current_version,
            current_code=current_code,
            current_description=current_strategy.describe(),
            performance_report=performance_report,
            recent_signals_summary=recent_signals,
            memory_context=memory_context or "No accumulated memory yet (early days).",
            human_guidance=human_guidance or "",
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            new_code = response.content[0].text.strip()

            # Strip markdown fences if Claude added them
            if new_code.startswith("```python"):
                new_code = new_code[len("```python"):].strip()
            if new_code.startswith("```"):
                new_code = new_code[3:].strip()
            if new_code.endswith("```"):
                new_code = new_code[:-3].strip()

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return {"evolved": False, "new_code": None, "new_version": None, "reason": f"API error: {e}", "source_suggestions": []}

        # Validate the new code
        logger.info("Validating new strategy code...")
        validation = self.validator.validate(new_code)
        if not validation["valid"]:
            logger.warning(f"New strategy failed validation: {validation['error']}")
            return {
                "evolved": False,
                "new_code": new_code,
                "new_version": None,
                "reason": f"Validation failed: {validation['error']}",
                "source_suggestions": [],
            }

        # Load and test the new strategy
        try:
            new_strategy = self.runner.load_strategy(new_code)
        except Exception as e:
            logger.warning(f"Failed to load new strategy: {e}")
            return {"evolved": False, "new_code": new_code, "new_version": None, "reason": f"Load failed: {e}", "source_suggestions": []}

        # Quick validation with sample signals
        quick_test = self.backtester.validate_strategy(new_strategy)
        if not quick_test["valid"]:
            logger.warning(f"New strategy failed quick test: {quick_test.get('error')}")
            return {
                "evolved": False,
                "new_code": new_code,
                "new_version": None,
                "reason": f"Quick test failed: {quick_test.get('error')}",
                "source_suggestions": [],
            }

        # Backtest against historical data
        backtest = self.backtester.backtest(new_strategy)
        if not backtest["passed"]:
            logger.warning("New strategy failed backtesting")
            return {
                "evolved": False,
                "new_code": new_code,
                "new_version": None,
                "reason": "Backtest failed — strategy produced no picks",
                "source_suggestions": [],
            }

        # Deploy!
        new_version = current_version + 1
        self.rollback.save_version(new_version, new_code, new_strategy.describe(), current_version)

        logger.info(f"Strategy evolved: v{current_version} → v{new_version}")
        logger.info(f"New strategy: {new_strategy.describe()[:200]}")

        # Also discover new sources
        source_suggestions = self.discover_sources(performance_report, memory_context)

        return {
            "evolved": True,
            "new_code": new_code,
            "new_version": new_version,
            "new_description": new_strategy.describe(),
            "backtest": backtest,
            "reason": "Evolution successful",
            "source_suggestions": source_suggestions,
        }

    def discover_sources(self, performance_report: str, memory_context: str) -> list[dict]:
        """Ask Claude to suggest new data sources to explore."""
        current_sources = "yfinance (stocks), RSS news feeds, Reddit (PRAW), SEC EDGAR, CoinGecko (crypto trending), yfinance crypto pairs"

        prompt = SOURCE_DISCOVERY_PROMPT.format(
            current_sources=current_sources,
            performance_report=performance_report,
            memory_context=memory_context or "No memory yet.",
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            # Extract JSON from response
            import json
            # Find JSON array in response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                suggestions = json.loads(text[start:end])
                logger.info(f"Source discovery found {len(suggestions)} suggestions")
                return suggestions
        except Exception as e:
            logger.debug(f"Source discovery failed: {e}")

        return []

    def _get_recent_signals_summary(self, days: int = 3) -> str:
        """Summarize recent signals for the evolution prompt."""
        from datetime import datetime, timedelta

        lines = []
        today = datetime.utcnow().date()

        for offset in range(days):
            date = today - timedelta(days=offset)
            signals = self.db.get_signals_for_date(date.isoformat())
            if signals:
                lines.append(f"\n--- {date.isoformat()} ({len(signals)} signals) ---")
                for s in signals[:10]:  # Cap at 10 per day
                    lines.append(f"  [{s['source']}] {s['ticker']}: {s['headline'][:80]} (sentiment: {s['sentiment']:.2f})")

        return "\n".join(lines) if lines else "No recent signals available (this may be the first run)."
