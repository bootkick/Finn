"""Tests for database layer."""

import tempfile
from pathlib import Path
from datetime import datetime

from finn.database import Database
from finn.models.signals import Signal, SignalType
from finn.models.picks import Pick, Conviction


def _make_db():
    tmp = tempfile.mktemp(suffix=".sqlite")
    return Database(Path(tmp))


def test_init_tables():
    db = _make_db()
    # Should not raise
    db.close()


def test_save_and_retrieve_signals():
    db = _make_db()
    signals = [
        Signal(source="test", signal_type=SignalType.PRICE, ticker="AAPL", headline="Up 5%", sentiment=0.5),
        Signal(source="test", signal_type=SignalType.NEWS, ticker="MSFT", headline="Good earnings", sentiment=0.8),
    ]
    db.save_signals(signals)

    today = datetime.utcnow().date().isoformat()
    rows = db.get_signals_for_date(today)
    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAPL"
    db.close()


def test_save_and_retrieve_pick():
    db = _make_db()
    pick = Pick(
        ticker="NVDA",
        conviction=Conviction.HIGH,
        direction="long",
        reasoning="Test",
        entry_price=500.0,
        strategy_version=1,
    )
    pick_id = db.save_pick(pick)
    assert pick_id > 0

    recent = db.get_recent_picks(days=1)
    assert len(recent) == 1
    assert recent[0]["ticker"] == "NVDA"
    db.close()


def test_strategy_versioning():
    db = _make_db()

    db.save_strategy_version(1, "code v1", "First strategy")
    db.save_strategy_version(2, "code v2", "Second strategy", parent_version=1)

    assert db.get_active_strategy_version() == 2
    assert db.get_strategy_source(1) == "code v1"
    assert db.get_strategy_source(2) == "code v2"

    versions = db.get_all_strategy_versions()
    assert len(versions) == 2
    db.close()


def test_performance_tracking():
    db = _make_db()
    pick = Pick(
        ticker="AAPL", conviction=Conviction.MEDIUM, entry_price=150.0, strategy_version=1
    )
    pick_id = db.save_pick(pick)
    db.save_performance(pick_id, pick)

    positions = db.get_open_positions()
    assert len(positions) == 1
    assert positions[0]["ticker"] == "AAPL"

    db.update_performance(pick_id, 155.0, 3.33, 2)
    positions = db.get_open_positions()
    assert positions[0]["return_pct"] == 3.33

    db.close_performance(pick_id, 160.0, 6.67, 5)
    positions = db.get_open_positions()
    assert len(positions) == 0
    db.close()
