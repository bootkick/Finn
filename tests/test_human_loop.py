"""Tests for human-in-the-loop system."""

import tempfile
from pathlib import Path

from finn.database import Database
from finn.human_loop import HumanInTheLoop


def _make_hitl():
    tmp = tempfile.mkdtemp()
    db = Database(Path(tmp) / "test.sqlite")
    hitl = HumanInTheLoop(db, Path(tmp))
    return hitl, db


def test_ask_and_answer():
    hitl, db = _make_hitl()

    q_id = hitl.ask("Should I focus on tech stocks?", "Low win rate on tech", "medium")
    assert q_id == "q_0001"

    pending = hitl.get_pending_questions()
    assert len(pending) == 1
    assert pending[0]["question"] == "Should I focus on tech stocks?"

    hitl.answer(q_id, "Yes, double down on semiconductor names")

    pending = hitl.get_pending_questions()
    assert len(pending) == 0

    answers = hitl.get_recent_answers()
    assert len(answers) == 1
    assert "semiconductor" in answers[0]["answer"]

    db.close()


def test_rate_limiting():
    hitl, db = _make_hitl()

    # Too early (day 1)
    assert hitl.should_ask_question(1) is False

    # Day 5, no pending, should be OK
    assert hitl.should_ask_question(5) is True

    # Ask a question
    hitl.ask("Test?", "", "low")

    # Already asked today
    assert hitl.should_ask_question(5) is False

    db.close()


def test_too_many_pending():
    hitl, db = _make_hitl()

    hitl.ask("Q1?", "", "low")
    hitl.ask("Q2?", "", "low")
    hitl.ask("Q3?", "", "low")

    # 3+ pending = stop asking
    assert hitl.should_ask_question(10) is False

    db.close()


def test_generate_question_signal_drought():
    hitl, db = _make_hitl()

    context = {
        "performance": {"win_rate": 0.5, "closed_positions": 3},
        "evolution_result": None,
        "signals_collected": 2,
        "day_number": 5,
        "strategy_version": 1,
    }
    q = hitl.generate_question(context)
    assert q is not None
    assert "signals" in q["question"].lower() or "sources" in q["question"].lower()

    db.close()


def test_format_answers_empty():
    hitl, db = _make_hitl()
    assert hitl.format_answers_for_evolution() == ""
    db.close()


def test_format_answers_with_data():
    hitl, db = _make_hitl()
    q_id = hitl.ask("Focus on crypto?", "", "low")
    hitl.answer(q_id, "Yes, especially BTC and ETH")

    result = hitl.format_answers_for_evolution()
    assert "Human Operator Guidance" in result
    assert "crypto" in result.lower()
    db.close()
