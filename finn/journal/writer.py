"""Journal writer — daily markdown changelog + memory system for Finn."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from finn.database import Database

logger = logging.getLogger(__name__)


class JournalWriter:
    """Writes daily journal entries and maintains Finn's memory.

    The journal serves dual purpose:
    1. Build in Public content (daily markdown files)
    2. Memory system for the evolution engine (DB-backed reflections)
    """

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
        trades_executed: list[dict] | None = None,
        human_questions: list[dict] | None = None,
        source_suggestions: list[dict] | None = None,
    ) -> str:
        """Write today's journal entry and return the content."""
        lines = [
            f"# Finn Daily Journal — {date}",
            "",
            f"*Generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
            f"*Day {self._get_day_number()} of the journey*",
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
                direction = "LONG" if pick.get("direction", "long") == "long" else "SHORT"
                lines.append(
                    f"- **{pick['ticker']}** ({direction}, {pick.get('conviction', 'medium')}): "
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

        # Trades
        if trades_executed:
            lines.append("## Trades Executed")
            for trade in trades_executed:
                mode = trade.get("mode", "PAPER")
                lines.append(
                    f"- [{mode}] {trade.get('side', '?').upper()} "
                    f"${trade.get('notional', 0):.2f} of **{trade['ticker']}** "
                    f"({trade.get('conviction', '?')} conviction) — {trade.get('status', '?')}"
                )
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

        # Source suggestions
        if source_suggestions:
            lines.append("## New Source Ideas")
            for s in source_suggestions:
                lines.append(f"- **{s.get('source', '?')}**: {s.get('reason', 'N/A')} (difficulty: {s.get('difficulty', '?')})")
            lines.append("")

        # Human-in-the-loop
        if human_questions:
            lines.append("## Questions for Human Operator")
            for q in human_questions:
                status = "ANSWERED" if q.get("answered") else "PENDING"
                lines.append(f"- [{status}] {q.get('question', '?')}")
                if q.get("answer"):
                    lines.append(f"  > {q['answer']}")
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

    def save_memory(self, date: str, memory_type: str, content: str) -> None:
        """Save a memory entry (reflection, lesson, insight)."""
        self.db.save_memory(date, memory_type, content)

        # Also save to file for easy browsing
        memory_dir = self.journal_path.parent / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        filepath = memory_dir / f"{date}_{memory_type}.md"
        filepath.write_text(f"# Finn Memory — {memory_type} — {date}\n\n{content}")

    def get_memory_context(self, limit: int = 7) -> str:
        """Get recent memories as context string for evolution/personality."""
        memories = self.db.get_recent_memories("reflection", limit)
        if not memories:
            return ""

        lines = []
        for m in memories:
            lines.append(f"### {m['date']}")
            lines.append(m["content"])
            lines.append("")

        return "\n".join(lines)

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
