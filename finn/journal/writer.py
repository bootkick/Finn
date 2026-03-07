"""Journal writer — daily markdown changelog for Build in Public."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from finn.database import Database

logger = logging.getLogger(__name__)


class JournalWriter:
    """Writes daily journal entries documenting Finn's evolution."""

    def __init__(self, db: Database, journal_path: Path):
        self.db = db
        self.journal_path = journal_path

    def write_daily_entry(
        self,
        date: str,
        signals_collected: int,
        picks_made: list[dict],
        performance_update: list[dict],
        evolution_result: dict | None,
        strategy_description: str,
    ) -> str:
        """Write today's journal entry and return the content."""
        lines = [
            f"# Finn Daily Journal — {date}",
            "",
            f"*Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
            "",
            "---",
            "",
            "## Signals Collected",
            f"Total signals processed: **{signals_collected}**",
            "",
        ]

        # Picks
        lines.append("## Today's Picks")
        if picks_made:
            for pick in picks_made:
                emoji_dir = "LONG" if pick.get("direction", "long") == "long" else "SHORT"
                lines.append(
                    f"- **{pick['ticker']}** ({emoji_dir}, {pick.get('conviction', 'medium')}): "
                    f"{pick.get('reasoning', 'N/A')[:150]}"
                )
        else:
            lines.append("*No picks generated today.*")
        lines.append("")

        # Performance
        lines.append("## Open Positions Update")
        if performance_update:
            lines.append("| Ticker | Direction | Return | Days Held |")
            lines.append("|--------|-----------|--------|-----------|")
            for pos in performance_update:
                lines.append(
                    f"| {pos['ticker']} | {pos.get('direction', 'long')} | "
                    f"{pos.get('return_pct', 0):+.1f}% | {pos.get('days_held', 0)} |"
                )
        else:
            lines.append("*No open positions to report.*")
        lines.append("")

        # Evolution
        lines.append("## Strategy Evolution")
        if evolution_result and evolution_result.get("evolved"):
            lines.append(f"**Strategy evolved to v{evolution_result['new_version']}!**")
            lines.append("")
            lines.append(f"Reason: {evolution_result.get('reason', 'N/A')}")
            lines.append("")
            if evolution_result.get("new_description"):
                lines.append("### New Strategy Description")
                lines.append(evolution_result["new_description"])
        elif evolution_result:
            lines.append(f"*Evolution attempted but not deployed: {evolution_result.get('reason', 'N/A')}*")
        else:
            lines.append("*No evolution cycle today (not enough data yet).*")
        lines.append("")

        # Current strategy
        lines.append("## Current Strategy")
        lines.append(strategy_description)
        lines.append("")

        lines.append("---")
        lines.append(f"*Finn v0.1.0 — Day {self._get_day_number()}*")

        content = "\n".join(lines)

        # Save to file
        filepath = self.journal_path / f"{date}.md"
        filepath.write_text(content)

        # Save to database
        self.db.save_journal_entry(date, content)

        logger.info(f"Journal entry written: {filepath}")
        return content

    def _get_day_number(self) -> int:
        """How many days has Finn been running?"""
        return max(1, self.db.get_total_days_with_picks())

    def get_recent_entries(self, count: int = 7) -> list[str]:
        """Get recent journal entries."""
        entries = []
        files = sorted(self.journal_path.glob("*.md"), reverse=True)[:count]
        for f in files:
            entries.append(f.read_text())
        return entries
