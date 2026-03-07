"""Tests for data models."""

from datetime import datetime

from finn.models.signals import Signal, SignalType
from finn.models.picks import Pick, Conviction
from finn.models.performance import PerformanceRecord, StrategyVersion


def test_signal_creation():
    signal = Signal(
        source="test",
        signal_type=SignalType.PRICE,
        ticker="AAPL",
        headline="Apple up 5%",
        sentiment=0.7,
        magnitude=0.5,
    )
    assert signal.ticker == "AAPL"
    assert signal.sentiment == 0.7
    assert "bullish" in signal.summary()


def test_signal_bearish():
    signal = Signal(
        source="test",
        signal_type=SignalType.NEWS,
        ticker="TSLA",
        headline="Tesla misses earnings",
        sentiment=-0.8,
        magnitude=0.6,
    )
    assert "bearish" in signal.summary()


def test_pick_creation():
    pick = Pick(
        ticker="NVDA",
        conviction=Conviction.HIGH,
        direction="long",
        reasoning="Strong AI demand signals",
        signals_used=5,
    )
    assert pick.ticker == "NVDA"
    assert pick.conviction == Conviction.HIGH
    assert "LONG" in pick.summary()


def test_performance_record_winner():
    record = PerformanceRecord(
        pick_id=1,
        ticker="AAPL",
        direction="long",
        entry_price=150.0,
        entry_date=datetime(2026, 3, 1),
        current_price=160.0,
        return_pct=6.67,
    )
    assert record.is_winner is True


def test_performance_record_loser():
    record = PerformanceRecord(
        pick_id=2,
        ticker="TSLA",
        direction="long",
        entry_price=200.0,
        entry_date=datetime(2026, 3, 1),
        current_price=180.0,
        return_pct=-10.0,
    )
    assert record.is_winner is False


def test_strategy_version():
    sv = StrategyVersion(
        version=1,
        source_code="class MyStrategy: pass",
        description="Test strategy",
    )
    assert sv.version == 1
    assert sv.is_active is True
