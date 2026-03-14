"""Tests for auto-trading module."""

import tempfile
from pathlib import Path

from finn.database import Database
from finn.trading import AutoTrader
from finn.models.picks import Pick, Conviction


def test_trader_not_available_without_keys():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trader = AutoTrader(api_key="", api_secret="", db=db)
    assert trader.is_available is False
    db.close()


def test_trader_available_with_keys():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trader = AutoTrader(api_key="test", api_secret="test", db=db)
    assert trader.is_available is True
    db.close()


def test_paper_mode_default():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trader = AutoTrader(api_key="test", api_secret="test", db=db)
    assert trader.paper is True
    assert "paper-api" in trader.base_url
    db.close()


def test_live_mode():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trader = AutoTrader(api_key="test", api_secret="test", db=db, paper=False)
    assert trader.paper is False
    assert "paper" not in trader.base_url
    db.close()


def test_execute_picks_no_keys():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trader = AutoTrader(api_key="", api_secret="", db=db)
    picks = [Pick(ticker="AAPL", conviction=Conviction.HIGH)]
    result = trader.execute_picks(picks)
    assert result == []
    db.close()


def test_db_trade_save():
    db = Database(Path(tempfile.mktemp(suffix=".sqlite")))
    trade = {
        "ticker": "AAPL",
        "side": "buy",
        "notional": 1000.0,
        "conviction": "high",
        "order_id": "test-123",
        "status": "submitted",
        "mode": "PAPER",
    }
    db.save_trade(trade)
    recent = db.get_recent_trades(1)
    assert len(recent) == 1
    assert recent[0]["ticker"] == "AAPL"
    db.close()
