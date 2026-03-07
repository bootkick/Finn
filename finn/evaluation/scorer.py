"""Strategy scorer — evaluates how well a strategy performed."""

from __future__ import annotations

import logging
import statistics

from finn.database import Database

logger = logging.getLogger(__name__)


class StrategyScorer:
    """Scores strategy performance for the evolution engine."""

    def __init__(self, db: Database):
        self.db = db

    def score_strategy(self, version: int) -> dict:
        """Comprehensive performance score for a strategy version."""
        perf = self.db.get_strategy_performance(version)

        return {
            "version": version,
            "total_picks": perf.get("total_picks", 0),
            "win_rate": perf.get("win_rate", 0.0),
            "avg_return": perf.get("avg_return", 0.0),
            "closed_positions": perf.get("closed", 0),
        }

    def compare_strategies(self, v1: int, v2: int) -> dict:
        """Compare two strategy versions."""
        s1 = self.score_strategy(v1)
        s2 = self.score_strategy(v2)

        return {
            "v1": s1,
            "v2": s2,
            "winner": v1 if self._composite_score(s1) >= self._composite_score(s2) else v2,
            "improvement": self._composite_score(s2) - self._composite_score(s1),
        }

    def generate_feedback(self, version: int) -> str:
        """Generate human-readable performance feedback for the evolution engine."""
        score = self.score_strategy(version)
        positions = self.db.get_open_positions()
        recent = self.db.get_recent_picks(days=14)

        lines = [
            f"Strategy v{version} Performance Report",
            f"{'=' * 40}",
            f"Total picks: {score['total_picks']}",
            f"Closed positions: {score['closed_positions']}",
            f"Win rate: {score['win_rate']:.1%}",
            f"Average return: {score['avg_return']:.2f}%",
            "",
        ]

        if positions:
            lines.append("Open positions:")
            for pos in positions:
                lines.append(
                    f"  {pos['ticker']} ({pos['direction']}): "
                    f"{pos.get('return_pct', 0):.1f}% over {pos.get('days_held', 0)} days"
                )
            lines.append("")

        # Identify patterns
        if score["closed_positions"] > 0:
            if score["win_rate"] < 0.4:
                lines.append("ISSUE: Win rate below 40% — strategy may be picking wrong direction")
            if score["avg_return"] < -2.0:
                lines.append("ISSUE: Average return deeply negative — reconsider signal weighting")
            if score["win_rate"] > 0.6:
                lines.append("STRENGTH: Win rate above 60% — directional logic is working")
            if score["avg_return"] > 1.0:
                lines.append("STRENGTH: Positive average returns — keep current approach")

        return "\n".join(lines)

    def _composite_score(self, score: dict) -> float:
        """Single composite score for comparing strategies."""
        if score["closed_positions"] == 0:
            return 0.0
        return (score["win_rate"] * 50) + (score["avg_return"] * 10)
