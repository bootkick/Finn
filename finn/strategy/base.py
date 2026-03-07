"""Strategy interface contract.

Every strategy — whether the initial v1 or a Claude-evolved v90 —
must implement this interface. This is the IMMUTABLE contract that
the MUTABLE strategy code adheres to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from finn.models.signals import Signal
from finn.models.picks import Pick


class Strategy(ABC):
    """The interface every strategy version must implement."""

    @abstractmethod
    def analyze(self, signals: list[Signal]) -> list[Pick]:
        """Given today's signals, return ranked picks.

        Args:
            signals: All collected signals for today.

        Returns:
            List of Pick objects, ordered by conviction (highest first).
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """Return a human-readable description of the current strategy logic.

        This gets logged in the daily journal so we can track how
        the strategy evolves over time.
        """
        ...
