"""Signal data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    PRICE = "price"
    VOLUME = "volume"
    NEWS = "news"
    SOCIAL = "social"
    FILING = "filing"
    TECHNICAL = "technical"


class Signal(BaseModel):
    """A single market signal from any source."""

    source: str  # e.g., "yfinance", "reddit", "sec_edgar", "rss"
    signal_type: SignalType
    ticker: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    headline: str = ""
    content: str = ""
    sentiment: float = 0.0  # -1.0 (bearish) to 1.0 (bullish)
    magnitude: float = 0.0  # 0.0 to 1.0 (strength of signal)
    metadata: dict = Field(default_factory=dict)

    def summary(self) -> str:
        """One-line summary for logging."""
        direction = "bullish" if self.sentiment > 0 else "bearish" if self.sentiment < 0 else "neutral"
        return f"[{self.source}] {self.ticker} {direction} ({self.sentiment:+.2f}): {self.headline[:80]}"
