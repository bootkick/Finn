"""Strategy execution with sandboxing and fallback."""

from __future__ import annotations

import importlib.util
import logging
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

from finn.models.signals import Signal
from finn.models.picks import Pick
from finn.strategy.base import Strategy

logger = logging.getLogger(__name__)

# Modules that strategy code is allowed to import
ALLOWED_IMPORTS = {
    "math", "statistics", "datetime", "collections", "itertools",
    "functools", "operator", "re", "json", "typing", "__future__",
}

STRATEGY_TIMEOUT_SECONDS = 30


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Strategy execution timed out")


class StrategyRunner:
    """Loads and executes strategy code with safety rails."""

    def __init__(self, strategies_path: Path):
        self.strategies_path = strategies_path
        self._fallback_strategy: Strategy | None = None

    def load_strategy(self, source_code: str) -> Strategy:
        """Load a strategy from source code string."""
        # Write to a temp file and import it
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=str(self.strategies_path)
        ) as f:
            f.write(source_code)
            f.flush()
            temp_path = f.name

        try:
            spec = importlib.util.spec_from_file_location("strategy_module", temp_path)
            module = importlib.util.module_from_spec(spec)

            # Restrict imports in the strategy module
            original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
            def restricted_import(name, *args, **kwargs):
                top_level = name.split(".")[0]
                if top_level not in ALLOWED_IMPORTS and top_level not in {"finn", "builtins"}:
                    raise ImportError(f"Import '{name}' is not allowed in strategy code. Allowed: {ALLOWED_IMPORTS}")
                return original_import(name, *args, **kwargs)

            if isinstance(__builtins__, dict):
                builtins_dict = dict(__builtins__)
            else:
                builtins_dict = {k: getattr(__builtins__, k) for k in dir(__builtins__)}
            builtins_dict["__import__"] = restricted_import
            module.__builtins__ = builtins_dict

            spec.loader.exec_module(module)

            # Find the Strategy subclass
            strategy_cls = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Strategy)
                    and attr is not Strategy
                ):
                    strategy_cls = attr
                    break

            if strategy_cls is None:
                raise ValueError("No Strategy subclass found in code")

            return strategy_cls()

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def run(self, strategy: Strategy, signals: list[Signal]) -> list[Pick]:
        """Execute strategy with timeout protection."""
        try:
            # Set timeout (Unix only)
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(STRATEGY_TIMEOUT_SECONDS)
        except (AttributeError, ValueError):
            # Windows or non-main thread — skip timeout
            old_handler = None

        try:
            picks = strategy.analyze(signals)
            return picks
        except TimeoutError:
            logger.error("Strategy execution timed out")
            return []
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            return []
        finally:
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (AttributeError, ValueError):
                pass

    def load_from_file(self, filepath: Path) -> Strategy:
        """Load strategy from a file path."""
        source_code = filepath.read_text()
        return self.load_strategy(source_code)
