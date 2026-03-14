"""Performance tracker — records picks and monitors outcomes."""

from __future__ import annotations

import logging
from datetime import datetime

from finn.database import Database
from finn.models.picks import Pick

logger = logging.getLogger(__name__)


def _get_current_price(ticker_symbol: str) -> float | None:
    """Get current price via Yahoo Finance HTTP API."""
    from finn.collectors.market_data import _yahoo_request, YAHOO_CHART_URL
    from finn.collectors.crypto import CRYPTO_COINS

    symbol = CRYPTO_COINS.get(ticker_symbol, ticker_symbol)
    try:
        url = YAHOO_CHART_URL.format(symbol=symbol)
        data = _yahoo_request(url)
        result = data.get("chart", {}).get("result", [])
        if result:
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            valid = [c for c in closes if c is not None]
            if valid:
                return float(valid[-1])
    except Exception:
        pass
    return None


class PerformanceTracker:
    """Tracks pick performance over time using market data."""

    def __init__(self, db: Database):
        self.db = db

    def record_pick(self, pick: Pick) -> int:
        """Record a new pick and its entry price."""
        pick_id = self.db.save_pick(pick)
        if pick.entry_price:
            self.db.save_performance(pick_id, pick)
        return pick_id

    def update_open_positions(self) -> list[dict]:
        """Update all open positions with current prices."""
        positions = self.db.get_open_positions()
        updated = []

        for pos in positions:
            try:
                current_price = _get_current_price(pos["ticker"])
                if current_price is None:
                    continue

                entry_price = pos["entry_price"]
                entry_date = datetime.fromisoformat(pos["entry_date"])
                days_held = (datetime.utcnow() - entry_date).days

                if pos["direction"] == "long":
                    return_pct = (current_price - entry_price) / entry_price * 100
                else:
                    return_pct = (entry_price - current_price) / entry_price * 100

                self.db.update_performance(
                    pos["pick_id"], current_price, return_pct, days_held
                )

                # Auto-close after 5 trading days
                if days_held >= 7:
                    self.db.close_performance(
                        pos["pick_id"], current_price, return_pct, days_held
                    )
                    logger.info(
                        f"Closed {pos['ticker']} after {days_held} days: {return_pct:+.1f}%"
                    )

                updated.append({
                    **pos,
                    "current_price": current_price,
                    "return_pct": return_pct,
                    "days_held": days_held,
                })
            except Exception as e:
                logger.warning(f"Failed to update {pos['ticker']}: {e}")

        return updated

    def get_performance_summary(self, strategy_version: int | None = None) -> dict:
        """Get performance summary for a strategy version."""
        if strategy_version is None:
            strategy_version = self.db.get_active_strategy_version()
        return self.db.get_strategy_performance(strategy_version)
