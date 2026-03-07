"""Tests for evolution engine components."""

from finn.evolution.validator import StrategyValidator


VALID_STRATEGY = '''
from finn.strategy.base import Strategy
from finn.models.signals import Signal, SignalType
from finn.models.picks import Pick, Conviction

class TestStrategy(Strategy):
    def analyze(self, signals: list[Signal]) -> list[Pick]:
        return []

    def describe(self) -> str:
        return "Test strategy"
'''

INVALID_NO_CLASS = '''
def analyze(signals):
    return []
'''

INVALID_BANNED_IMPORT = '''
import os
from finn.strategy.base import Strategy
from finn.models.signals import Signal
from finn.models.picks import Pick, Conviction

class BadStrategy(Strategy):
    def analyze(self, signals: list[Signal]) -> list[Pick]:
        os.system("rm -rf /")
        return []

    def describe(self) -> str:
        return "Evil"
'''

INVALID_USES_EXEC = '''
from finn.strategy.base import Strategy
from finn.models.signals import Signal
from finn.models.picks import Pick, Conviction

class BadStrategy(Strategy):
    def analyze(self, signals: list[Signal]) -> list[Pick]:
        exec("print('hacked')")
        return []

    def describe(self) -> str:
        return "Evil"
'''

INVALID_MISSING_METHOD = '''
from finn.strategy.base import Strategy
from finn.models.signals import Signal
from finn.models.picks import Pick, Conviction

class IncompleteStrategy(Strategy):
    def analyze(self, signals: list[Signal]) -> list[Pick]:
        return []
'''


def test_valid_strategy():
    validator = StrategyValidator()
    result = validator.validate(VALID_STRATEGY)
    assert result["valid"] is True
    assert result["error"] is None


def test_invalid_no_class():
    validator = StrategyValidator()
    result = validator.validate(INVALID_NO_CLASS)
    assert result["valid"] is False
    assert "Strategy" in result["error"]


def test_banned_import():
    validator = StrategyValidator()
    result = validator.validate(INVALID_BANNED_IMPORT)
    assert result["valid"] is False
    assert "Banned import" in result["error"]


def test_banned_exec():
    validator = StrategyValidator()
    result = validator.validate(INVALID_USES_EXEC)
    assert result["valid"] is False
    assert "exec" in result["error"]


def test_missing_describe():
    validator = StrategyValidator()
    result = validator.validate(INVALID_MISSING_METHOD)
    assert result["valid"] is False
    assert "describe" in result["error"]


def test_syntax_error():
    validator = StrategyValidator()
    result = validator.validate("def broken(:\n    pass")
    assert result["valid"] is False
    assert "Syntax" in result["error"]
