"""Human-in-the-loop system — non-blocking questions for the operator."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from finn.database import Database

logger = logging.getLogger(__name__)


class HumanInTheLoop:
    """Non-blocking question/answer system between Finn and its human operator.

    Finn can ask questions when it hits a wall or wants guidance.
    The human answers when convenient — no blocking. Finn checks
    for answers on the next run and incorporates them.
    """

    def __init__(self, db: Database, data_path: Path):
        self.db = db
        self.questions_file = data_path / "human_questions.json"
        self._ensure_file()

    def _ensure_file(self):
        if not self.questions_file.exists():
            self.questions_file.write_text(json.dumps({"questions": []}, indent=2))

    def _load(self) -> dict:
        return json.loads(self.questions_file.read_text())

    def _save(self, data: dict):
        self.questions_file.write_text(json.dumps(data, indent=2))

    def ask(self, question: str, context: str = "", priority: str = "low") -> str:
        """Finn asks a question. Returns the question ID.

        Priority levels:
        - "low": Nice to have, Finn can work without it
        - "medium": Would help improve next evolution
        - "high": Finn is stuck or confused about something important
        """
        data = self._load()
        q_id = f"q_{len(data['questions']) + 1:04d}"

        data["questions"].append({
            "id": q_id,
            "question": question,
            "context": context,
            "priority": priority,
            "asked_at": datetime.utcnow().isoformat(),
            "answered": False,
            "answer": None,
            "answered_at": None,
        })

        self._save(data)
        logger.info(f"Finn asked [{priority}]: {question}")
        return q_id

    def get_pending_questions(self) -> list[dict]:
        """Get all unanswered questions."""
        data = self._load()
        return [q for q in data["questions"] if not q["answered"]]

    def get_recent_answers(self, since_days: int = 7) -> list[dict]:
        """Get recently answered questions to feed into evolution context."""
        data = self._load()
        cutoff = datetime.utcnow().isoformat()
        answered = [
            q for q in data["questions"]
            if q["answered"] and q.get("answer")
        ]
        return answered[-10:]  # Last 10 answers

    def answer(self, question_id: str, answer: str) -> bool:
        """Human answers a question."""
        data = self._load()
        for q in data["questions"]:
            if q["id"] == question_id:
                q["answered"] = True
                q["answer"] = answer
                q["answered_at"] = datetime.utcnow().isoformat()
                self._save(data)
                logger.info(f"Question {question_id} answered: {answer[:100]}")
                return True
        return False

    def should_ask_question(self, day_number: int) -> bool:
        """Rate-limit questions — don't pester the human too much.

        Rules:
        - Max 1 question per day
        - Only after day 3 (give Finn time to learn first)
        - Skip if there are already 3+ unanswered questions
        """
        if day_number < 3:
            return False

        pending = self.get_pending_questions()
        if len(pending) >= 3:
            return False

        # Check if already asked today
        today = datetime.utcnow().date().isoformat()
        for q in pending:
            if q["asked_at"].startswith(today):
                return False

        return True

    def generate_question(self, context: dict) -> dict | None:
        """Generate a relevant question based on current context.

        Returns {"question": str, "context": str, "priority": str} or None
        """
        # Check for specific trigger conditions
        perf = context.get("performance", {})
        win_rate = perf.get("win_rate", 0)
        evolution_result = context.get("evolution_result")
        signals_collected = context.get("signals_collected", 0)

        # Struggling with performance
        if win_rate < 0.3 and perf.get("closed_positions", 0) >= 5:
            return {
                "question": "My win rate is rough right now. Are there specific sectors or market conditions you think I should be paying more attention to?",
                "context": f"Current win rate: {win_rate:.0%}, Avg return: {perf.get('avg_return', 0):.1f}%",
                "priority": "medium",
            }

        # Signal drought
        if signals_collected < 5:
            return {
                "question": "I'm not getting many signals today. Are there any news sources, subreddits, or data feeds you'd recommend I try to pull from?",
                "context": f"Only {signals_collected} signals collected today",
                "priority": "medium",
            }

        # Evolution failed
        if evolution_result and not evolution_result.get("evolved"):
            reason = evolution_result.get("reason", "unknown")
            if "validation" in reason.lower() or "failed" in reason.lower():
                return {
                    "question": "My evolution attempt failed validation. Any thoughts on what kind of strategy approaches you'd like me to explore?",
                    "context": f"Evolution failure reason: {reason}",
                    "priority": "low",
                }

        # Periodic check-in (every 10 days)
        day = context.get("day_number", 0)
        if day > 0 and day % 10 == 0:
            return {
                "question": f"Day {day} check-in! How do you feel about my progress so far? Any new tickers, sectors, or strategies you want me to explore?",
                "context": f"Day {day}, strategy v{context.get('strategy_version', '?')}",
                "priority": "low",
            }

        return None

    def format_answers_for_evolution(self) -> str:
        """Format recent human answers as context for the evolution engine."""
        answers = self.get_recent_answers()
        if not answers:
            return ""

        lines = ["## Human Operator Guidance"]
        for a in answers:
            lines.append(f"- Q: {a['question']}")
            lines.append(f"  A: {a['answer']}")
            lines.append("")

        return "\n".join(lines)
