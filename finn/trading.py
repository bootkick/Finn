"""Auto-trading integration via Alpaca API.

IMPORTANT: This module executes REAL trades when enabled.
Use paper trading mode first. Finn is an experiment, not a financial advisor.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime

from finn.database import Database
from finn.models.picks import Pick, Conviction

logger = logging.getLogger(__name__)


class AutoTrader:
    """Executes trades via Alpaca API based on Finn's picks.

    Supports paper trading (default) and live trading.
    Has position sizing, risk limits, and kill switch.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db: Database,
        paper: bool = True,
        max_position_pct: float = 0.10,  # Max 10% of portfolio per position
        max_daily_trades: int = 5,
        max_portfolio_risk_pct: float = 0.50,  # Max 50% of portfolio in active trades
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.db = db
        self.paper = paper
        self.max_position_pct = max_position_pct
        self.max_daily_trades = max_daily_trades
        self.max_portfolio_risk_pct = max_portfolio_risk_pct

        self.base_url = (
            "https://paper-api.alpaca.markets"
            if paper
            else "https://api.alpaca.markets"
        )

        self._daily_trade_count = 0

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _api_request(self, method: str, endpoint: str, body: dict | None = None) -> dict:
        """Make authenticated request to Alpaca API."""
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("APCA-API-KEY-ID", self.api_key)
        req.add_header("APCA-API-SECRET-KEY", self.api_secret)
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def get_account(self) -> dict:
        """Get current account info."""
        return self._api_request("GET", "/v2/account")

    def get_positions(self) -> list[dict]:
        """Get current open positions."""
        return self._api_request("GET", "/v2/positions")

    def execute_picks(self, picks: list[Pick]) -> list[dict]:
        """Execute trades based on Finn's picks.

        Only trades HIGH and MEDIUM conviction picks.
        Respects all risk limits.
        """
        if not self.is_available:
            logger.info("Auto-trading not configured, skipping")
            return []

        results = []

        try:
            account = self.get_account()
            portfolio_value = float(account.get("portfolio_value", 0))
            buying_power = float(account.get("buying_power", 0))

            if portfolio_value <= 0:
                logger.warning("No portfolio value, skipping trades")
                return results

            # Check existing positions
            positions = self.get_positions()
            existing_tickers = {p["symbol"] for p in positions}
            total_position_value = sum(
                abs(float(p.get("market_value", 0))) for p in positions
            )
            portfolio_usage = total_position_value / portfolio_value

            if portfolio_usage >= self.max_portfolio_risk_pct:
                logger.info(
                    f"Portfolio {portfolio_usage:.0%} allocated (max {self.max_portfolio_risk_pct:.0%}), no new trades"
                )
                return results

            # Filter to tradeable picks
            tradeable = [
                p for p in picks
                if p.conviction in (Conviction.HIGH, Conviction.MEDIUM)
                and p.ticker not in existing_tickers
                and p.ticker.isalpha()  # Skip crypto tickers with special chars
            ]

            for pick in tradeable:
                if self._daily_trade_count >= self.max_daily_trades:
                    logger.info("Daily trade limit reached")
                    break

                try:
                    result = self._execute_single(pick, portfolio_value, buying_power)
                    if result:
                        results.append(result)
                        self._daily_trade_count += 1
                except Exception as e:
                    logger.warning(f"Trade failed for {pick.ticker}: {e}")
                    results.append({
                        "ticker": pick.ticker,
                        "status": "failed",
                        "error": str(e),
                    })

        except Exception as e:
            logger.error(f"Auto-trading failed: {e}")

        return results

    def _execute_single(self, pick: Pick, portfolio_value: float, buying_power: float) -> dict | None:
        """Execute a single trade."""
        # Position sizing based on conviction
        if pick.conviction == Conviction.HIGH:
            position_pct = self.max_position_pct
        else:
            position_pct = self.max_position_pct * 0.5  # Half size for medium

        target_value = portfolio_value * position_pct
        target_value = min(target_value, buying_power * 0.95)  # Leave 5% buffer

        if target_value < 1.0:
            return None

        # Build order
        side = "buy" if pick.direction == "long" else "sell"
        order = {
            "symbol": pick.ticker,
            "notional": str(round(target_value, 2)),  # Dollar amount
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }

        mode_label = "PAPER" if self.paper else "LIVE"
        logger.info(
            f"[{mode_label}] {side.upper()} ${target_value:.2f} of {pick.ticker} "
            f"({pick.conviction.value} conviction)"
        )

        result = self._api_request("POST", "/v2/orders", order)

        return {
            "ticker": pick.ticker,
            "side": side,
            "notional": target_value,
            "conviction": pick.conviction.value,
            "order_id": result.get("id"),
            "status": result.get("status", "submitted"),
            "mode": mode_label,
        }

    def close_position(self, ticker: str) -> dict | None:
        """Close a specific position."""
        try:
            return self._api_request("DELETE", f"/v2/positions/{ticker}")
        except Exception as e:
            logger.warning(f"Failed to close {ticker}: {e}")
            return None

    def close_all(self) -> dict:
        """Emergency kill switch — close ALL positions."""
        logger.warning("KILL SWITCH: Closing all positions")
        return self._api_request("DELETE", "/v2/positions")
