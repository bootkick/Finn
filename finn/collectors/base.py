"""Base collector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from finn.models.signals import Signal


class BaseCollector(ABC):
    """Abstract base for all signal collectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this collector."""
        ...

    @abstractmethod
    def collect(self, tickers: list[str]) -> list[Signal]:
        """Collect signals for the given tickers."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this collector has the required API keys / dependencies."""
        return True
