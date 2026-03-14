"""Market data collector using Yahoo Finance HTTP API (no yfinance dependency)."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"


def _yahoo_request(url: str) -> dict:
    """Make a request to Yahoo Finance API."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Finn Financial Agent)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


class MarketDataCollector(BaseCollector):
    """Collects price, volume, and technical signals from Yahoo Finance."""

    @property
    def name(self) -> str:
        return "yahoo_finance"

    def collect(self, tickers: list[str]) -> list[Signal]:
        signals = []
        for ticker_symbol in tickers:
            try:
                signals.extend(self._collect_ticker(ticker_symbol))
            except Exception as e:
                logger.warning(f"Failed to collect market data for {ticker_symbol}: {e}")
        return signals

    def _collect_ticker(self, ticker_symbol: str) -> list[Signal]:
        signals = []
        url = YAHOO_CHART_URL.format(symbol=ticker_symbol)
        data = _yahoo_request(url)

        result = data.get("chart", {}).get("result", [])
        if not result:
            return signals

        chart = result[0]
        quotes = chart.get("indicators", {}).get("quote", [{}])[0]
        timestamps = chart.get("timestamp", [])

        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])

        # Filter out None values
        valid_closes = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        valid_volumes = [v for v in volumes if v is not None]

        if len(valid_closes) < 2:
            return signals

        latest_price = valid_closes[-1][1]
        prev_price = valid_closes[-2][1]

        # Price change signal
        price_change = (latest_price - prev_price) / prev_price
        signals.append(
            Signal(
                source="yahoo_finance",
                signal_type=SignalType.PRICE,
                ticker=ticker_symbol,
                headline=f"{ticker_symbol} {'up' if price_change > 0 else 'down'} {abs(price_change)*100:.1f}%",
                sentiment=max(-1.0, min(1.0, price_change * 10)),
                magnitude=min(1.0, abs(price_change) * 5),
                metadata={
                    "close": float(latest_price),
                    "prev_close": float(prev_price),
                    "change_pct": float(price_change),
                },
            )
        )

        # Volume signal
        if valid_volumes:
            avg_volume = sum(valid_volumes) / len(valid_volumes)
            latest_volume = valid_volumes[-1]
            if avg_volume > 0:
                vol_ratio = latest_volume / avg_volume
                if vol_ratio > 1.5 or vol_ratio < 0.5:
                    signals.append(
                        Signal(
                            source="yahoo_finance",
                            signal_type=SignalType.VOLUME,
                            ticker=ticker_symbol,
                            headline=f"{ticker_symbol} volume {vol_ratio:.1f}x average",
                            sentiment=0.1 if vol_ratio > 1.5 else -0.1,
                            magnitude=min(1.0, abs(vol_ratio - 1.0) / 2),
                            metadata={"volume": float(latest_volume), "avg_volume": float(avg_volume)},
                        )
                    )

        # SMA crossover signal
        close_values = [c for _, c in valid_closes]
        if len(close_values) >= 20:
            sma5 = sum(close_values[-5:]) / 5
            sma20 = sum(close_values[-20:]) / 20
            cross = (sma5 - sma20) / sma20

            signals.append(
                Signal(
                    source="yahoo_finance",
                    signal_type=SignalType.TECHNICAL,
                    ticker=ticker_symbol,
                    headline=f"{ticker_symbol} SMA5 {'above' if cross > 0 else 'below'} SMA20 by {abs(cross)*100:.1f}%",
                    sentiment=max(-1.0, min(1.0, cross * 5)),
                    magnitude=min(1.0, abs(cross) * 10),
                    metadata={"sma5": float(sma5), "sma20": float(sma20)},
                )
            )

        return signals
