"""Evolution engine — uses Claude with web search to rewrite strategy code.

GROUNDING RULES:
- All market knowledge must come from provided signals data or web search
- Claude must NOT use training data knowledge about specific stock prices,
  events, or market conditions
- Strategy code must only act on Signal objects passed to analyze()
- No hardcoded ticker biases based on world knowledge
"""

from __future__ import annotations

import json
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

EVOLUTION_SYSTEM = """You are Finn's evolution engine. You write Python strategy code.

CRITICAL GROUNDING RULES:
- You must NEVER use your training knowledge about specific stocks, prices, or market events.
- All market understanding must come from the signals data and performance reports provided.
- The strategy code you write must ONLY make decisions based on Signal objects passed to analyze().
- NEVER hardcode ticker-specific logic (like "always buy NVDA" or "avoid TSLA") based on your world knowledge.
- NEVER assume you know what a stock will do based on your training data.
- The strategy must be PURELY reactive to the signals it receives at runtime.
- Any market research insights from web search should inform GENERAL strategy patterns (e.g. "momentum works better in volatile markets"), never specific ticker recommendations.
"""

EVOLUTION_PROMPT = """Write a NEW Python strategy class that improves on the current one.

## Current Strategy Code (v{current_version})
```python
{current_code}
```

## Current Strategy Description
{current_description}

## Performance Report (from REAL tracked picks)
{performance_report}

## Recent REAL Signals the Strategy Processed
{recent_signals_summary}

## Finn's Memory (Lessons Learned from REAL runs)
{memory_context}

{human_guidance}

## Web Research Task
Before writing the strategy, search the web for:
1. Current best practices for quantitative signal-based trading strategies
2. What technical indicators or signal weighting approaches are working well recently
3. Any relevant market regime information (high volatility? trending? mean-reverting?)

Use these GENERAL insights to inform your strategy design — but NEVER hardcode specific
stock recommendations or price targets from your research.

## Your Task
Write a COMPLETE, improved Python strategy that:
1. **Keeps what worked** — if win rate is good, preserve the core logic
2. **Fixes what failed** — address the specific issues in the performance report
3. **Tries something new** — introduce ONE meaningful change based on your web research
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
- describe() should explain your SPECIFIC changes, reasoning, AND what web research informed the change
- NEVER hardcode ticker-specific biases — the strategy must work purely from signal data
- Keep it practical — no theoretical perfection, just measurable improvement

## Important
- Return ONLY the Python code, no markdown fences, no explanation outside the code
- The code must be syntactically valid and complete
- Include a docstring at the top explaining what changed from the previous version
"""

SOURCE_DISCOVERY_PROMPT = """You are Finn's source discovery engine. Search the web for new FREE data sources that could improve a quantitative trading signal pipeline.

## Current Signal Sources
{current_sources}

## Recent Performance
{performance_report}

## Recent Memory
{memory_context}

## Your Task
Search the web for freely available financial data APIs, RSS feeds, or public datasets.
Then suggest 1-3 new data sources Finn should explore. For each:
1. What is the source? (specific URL, API, data type)
2. Why would it help? (what gap does it fill based on the performance report?)
3. How hard is it to implement? (easy/medium/hard)

IMPORTANT: Only suggest sources you have VERIFIED exist via web search. Do not hallucinate APIs or URLs.

Return a JSON array of suggestions:
[{{"source": "...", "reason": "...", "difficulty": "...", "url_or_endpoint": "..."}}]
"""


class EvolutionEngine:
    """Uses Claude API with web search to evolve strategy code."""

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
        """Attempt to evolve the current strategy using web-grounded research."""
        current_version = self.db.get_active_strategy_version()
        performance_report = self.scorer.generate_feedback(current_version)
        recent_signals = self._get_recent_signals_summary()

        logger.info(f"Asking Claude (with web search) to evolve strategy v{current_version}...")

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
            # Use web search tool so Claude can research latest strategy techniques
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8096,
                system=EVOLUTION_SYSTEM,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract the text content (skip web search result blocks)
            new_code = ""
            for block in response.content:
                if hasattr(block, "text"):
                    new_code = block.text.strip()

            if not new_code:
                return {"evolved": False, "new_code": None, "new_version": None,
                        "reason": "No code in response", "source_suggestions": []}

            # Strip markdown fences if Claude added them
            if new_code.startswith("```python"):
                new_code = new_code[len("```python"):].strip()
            if new_code.startswith("```"):
                new_code = new_code[3:].strip()
            if new_code.endswith("```"):
                new_code = new_code[:-3].strip()

        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return {"evolved": False, "new_code": None, "new_version": None,
                    "reason": f"API error: {e}", "source_suggestions": []}

        # Validate the new code
        logger.info("Validating new strategy code...")
        validation = self.validator.validate(new_code)
        if not validation["valid"]:
            logger.warning(f"New strategy failed validation: {validation['error']}")
            return {"evolved": False, "new_code": new_code, "new_version": None,
                    "reason": f"Validation failed: {validation['error']}", "source_suggestions": []}

        # Load and test the new strategy
        try:
            new_strategy = self.runner.load_strategy(new_code)
        except Exception as e:
            logger.warning(f"Failed to load new strategy: {e}")
            return {"evolved": False, "new_code": new_code, "new_version": None,
                    "reason": f"Load failed: {e}", "source_suggestions": []}

        # Quick validation
        quick_test = self.backtester.validate_strategy(new_strategy)
        if not quick_test["valid"]:
            logger.warning(f"New strategy failed quick test: {quick_test.get('error')}")
            return {"evolved": False, "new_code": new_code, "new_version": None,
                    "reason": f"Quick test failed: {quick_test.get('error')}", "source_suggestions": []}

        # Backtest against real historical data
        backtest = self.backtester.backtest(new_strategy)
        if not backtest["passed"]:
            logger.warning("New strategy failed backtesting")
            return {"evolved": False, "new_code": new_code, "new_version": None,
                    "reason": "Backtest failed — strategy produced no picks", "source_suggestions": []}

        # Deploy!
        new_version = current_version + 1
        self.rollback.save_version(new_version, new_code, new_strategy.describe(), current_version)

        logger.info(f"Strategy evolved: v{current_version} → v{new_version}")
        logger.info(f"New strategy: {new_strategy.describe()[:200]}")

        # Discover new sources (also web-grounded)
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
        """Ask Claude with web search to find real, verified data sources."""
        current_sources = (
            "Yahoo Finance HTTP API (stocks + crypto prices/volume/technicals), "
            "Google News RSS (headlines), Yahoo Finance quote API (52-week range), "
            "SEC EDGAR EFTS (filings search), CoinGecko (crypto trending), "
            "Reddit via PRAW (social sentiment, requires API key)"
        )

        prompt = SOURCE_DISCOVERY_PROMPT.format(
            current_sources=current_sources,
            performance_report=performance_report,
            memory_context=memory_context or "No memory yet.",
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from response
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text.strip()

            if text:
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
        """Summarize recent REAL signals for the evolution prompt."""
        from datetime import datetime, timedelta

        lines = []
        today = datetime.utcnow().date()

        for offset in range(days):
            date = today - timedelta(days=offset)
            signals = self.db.get_signals_for_date(date.isoformat())
            if signals:
                lines.append(f"\n--- {date.isoformat()} ({len(signals)} signals) ---")
                for s in signals[:10]:
                    lines.append(f"  [{s['source']}] {s['ticker']}: {s['headline'][:80]} (sentiment: {s['sentiment']:.2f})")

        return "\n".join(lines) if lines else "No recent signals available (this may be the first run)."
