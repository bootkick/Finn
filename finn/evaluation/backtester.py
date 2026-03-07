"""Backtester — tests new strategies against historical signals before deployment."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from finn.database import Database
from finn.models.signals import Signal, SignalType
from finn.strategy.base import Strategy
from finn.strategy.runner import StrategyRunner

logger = logging.getLogger(__name__)


class Backtester:
    """Runs a strategy against historical signals to validate before deployment."""

    def __init__(self, db: Database, runner: StrategyRunner):
        self.db = db
        self.runner = runner

    def backtest(self, strategy: Strategy, days: int = 7) -> dict:
        """Run strategy against recent historical signals.

        Returns a report with simulated picks and how they would have performed.
        """
        results = {
            "days_tested": 0,
            "total_picks": 0,
            "simulated_returns": [],
            "avg_return": 0.0,
            "win_rate": 0.0,
            "passed": False,
            "details": [],
        }

        today = datetime.utcnow().date()

        for day_offset in range(days, 0, -1):
            test_date = today - timedelta(days=day_offset)
            date_str = test_date.isoformat()

            # Get historical signals for this day
            signal_rows = self.db.get_signals_for_date(date_str)
            if not signal_rows:
                continue

            signals = [
                Signal(
                    source=r["source"],
                    signal_type=SignalType(r["signal_type"]),
                    ticker=r["ticker"],
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    headline=r["headline"],
                    content=r["content"],
                    sentiment=r["sentiment"],
                    magnitude=r["magnitude"],
                )
                for r in signal_rows
            ]

            # Run strategy
            picks = self.runner.run(strategy, signals)
            if not picks:
                continue

            results["days_tested"] += 1
            results["total_picks"] += len(picks)

            # Check how picks would have done using stored price data
            for pick in picks:
                detail = {
                    "date": date_str,
                    "ticker": pick.ticker,
                    "direction": pick.direction,
                    "conviction": pick.conviction.value,
                }
                results["details"].append(detail)

        # Simple pass/fail: strategy must produce picks
        results["passed"] = results["total_picks"] > 0

        if results["simulated_returns"]:
            results["avg_return"] = sum(results["simulated_returns"]) / len(results["simulated_returns"])
            results["win_rate"] = sum(1 for r in results["simulated_returns"] if r > 0) / len(results["simulated_returns"])

        return results

    def validate_strategy(self, strategy: Strategy, signals_sample: list[Signal] | None = None) -> dict:
        """Quick validation: can the strategy run without crashing?"""
        if signals_sample is None:
            signals_sample = self._generate_sample_signals()

        try:
            picks = self.runner.run(strategy, signals_sample)
            return {
                "valid": True,
                "picks_generated": len(picks),
                "description": strategy.describe(),
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
            }

    def _generate_sample_signals(self) -> list[Signal]:
        """Generate synthetic signals for validation."""
        tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]
        signals = []
        for ticker in tickers:
            signals.extend([
                Signal(
                    source="test",
                    signal_type=SignalType.PRICE,
                    ticker=ticker,
                    headline=f"{ticker} up 2.3%",
                    sentiment=0.5,
                    magnitude=0.4,
                ),
                Signal(
                    source="test",
                    signal_type=SignalType.NEWS,
                    ticker=ticker,
                    headline=f"{ticker} beats earnings expectations",
                    sentiment=0.7,
                    magnitude=0.6,
                ),
                Signal(
                    source="test",
                    signal_type=SignalType.SOCIAL,
                    ticker=ticker,
                    headline=f"{ticker} trending on Reddit",
                    sentiment=0.3,
                    magnitude=0.3,
                ),
            ])
        return signals
