"""Tests for strategy engine."""

from pathlib import Path

from finn.models.signals import Signal, SignalType
from finn.models.picks import Conviction
from finn.strategy.runner import StrategyRunner


def _sample_signals():
    return [
        Signal(source="test", signal_type=SignalType.PRICE, ticker="AAPL", headline="AAPL up 3%", sentiment=0.6, magnitude=0.5),
        Signal(source="test", signal_type=SignalType.NEWS, ticker="AAPL", headline="Apple beats earnings", sentiment=0.8, magnitude=0.7),
        Signal(source="test", signal_type=SignalType.SOCIAL, ticker="AAPL", headline="AAPL trending", sentiment=0.4, magnitude=0.3),
        Signal(source="test", signal_type=SignalType.PRICE, ticker="TSLA", headline="TSLA down 5%", sentiment=-0.7, magnitude=0.6),
        Signal(source="test", signal_type=SignalType.NEWS, ticker="TSLA", headline="Tesla misses delivery targets", sentiment=-0.8, magnitude=0.8),
        Signal(source="test", signal_type=SignalType.PRICE, ticker="NVDA", headline="NVDA up 1%", sentiment=0.2, magnitude=0.2),
    ]


def test_v1_strategy_loads():
    v1_path = Path(__file__).parent.parent / "finn" / "strategy" / "active" / "strategy_v1.py"
    code = v1_path.read_text()

    import tempfile
    tmp = Path(tempfile.mkdtemp())
    runner = StrategyRunner(tmp)
    strategy = runner.load_strategy(code)

    assert strategy is not None
    assert hasattr(strategy, "analyze")
    assert hasattr(strategy, "describe")


def test_v1_strategy_generates_picks():
    v1_path = Path(__file__).parent.parent / "finn" / "strategy" / "active" / "strategy_v1.py"
    code = v1_path.read_text()

    import tempfile
    tmp = Path(tempfile.mkdtemp())
    runner = StrategyRunner(tmp)
    strategy = runner.load_strategy(code)

    picks = runner.run(strategy, _sample_signals())
    assert len(picks) > 0

    # AAPL should be a pick (strongest bullish signals)
    tickers = [p.ticker for p in picks]
    assert "AAPL" in tickers

    # Check picks have required fields
    for pick in picks:
        assert pick.ticker
        assert pick.conviction in [Conviction.HIGH, Conviction.MEDIUM, Conviction.LOW]
        assert pick.direction in ["long", "short"]


def test_v1_strategy_describe():
    v1_path = Path(__file__).parent.parent / "finn" / "strategy" / "active" / "strategy_v1.py"
    code = v1_path.read_text()

    import tempfile
    tmp = Path(tempfile.mkdtemp())
    runner = StrategyRunner(tmp)
    strategy = runner.load_strategy(code)

    desc = strategy.describe()
    assert len(desc) > 20
    assert "V1" in desc


def test_empty_signals_no_crash():
    v1_path = Path(__file__).parent.parent / "finn" / "strategy" / "active" / "strategy_v1.py"
    code = v1_path.read_text()

    import tempfile
    tmp = Path(tempfile.mkdtemp())
    runner = StrategyRunner(tmp)
    strategy = runner.load_strategy(code)

    picks = runner.run(strategy, [])
    assert picks == []
