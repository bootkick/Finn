"""Performance tracking models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PerformanceRecord(BaseModel):
    """Tracks the outcome of a pick over time."""

    pick_id: int
    ticker: str
    direction: str
    entry_price: float
    entry_date: datetime
    current_price: float | None = None
    exit_price: float | None = None
    exit_date: datetime | None = None
    return_pct: float = 0.0
    days_held: int = 0
    strategy_version: int = 1
    is_closed: bool = False

    @property
    def is_winner(self) -> bool:
        if self.direction == "long":
            return self.return_pct > 0
        return self.return_pct < 0  # short wins on negative return


class StrategyVersion(BaseModel):
    """Metadata about a strategy version."""

    version: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_code: str = ""
    description: str = ""
    parent_version: int | None = None
    performance_summary: str = ""
    total_picks: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    is_active: bool = True
