"""Market data collector using yfinance."""

from __future__ import annotations

import logging
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)


class MarketDataCollector(BaseCollector):
    """Collects price, volume, and technical signals from Yahoo Finance."""

    @property
    def name(self) -> str:
        return "yfinance"

    def collect(self, tickers: list[str]) -> list[Signal]:
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed, skipping market data")
            return []

        signals = []
        for ticker_symbol in tickers:
            try:
                signals.extend(self._collect_ticker(yf, ticker_symbol))
            except Exception as e:
                logger.warning(f"Failed to collect market data for {ticker_symbol}: {e}")
        return signals

    def _collect_ticker(self, yf, ticker_symbol: str) -> list[Signal]:
        signals = []
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period="1mo")

        if hist.empty:
            return signals

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest

        # Price change signal
        price_change = (latest["Close"] - prev["Close"]) / prev["Close"]
        signals.append(
            Signal(
                source="yfinance",
                signal_type=SignalType.PRICE,
                ticker=ticker_symbol,
                headline=f"{ticker_symbol} {'up' if price_change > 0 else 'down'} {abs(price_change)*100:.1f}%",
                sentiment=max(-1.0, min(1.0, price_change * 10)),  # scale to [-1, 1]
                magnitude=min(1.0, abs(price_change) * 5),
                metadata={
                    "close": float(latest["Close"]),
                    "prev_close": float(prev["Close"]),
                    "change_pct": float(price_change),
                },
            )
        )

        # Volume signal
        avg_volume = hist["Volume"].mean()
        vol_ratio = latest["Volume"] / avg_volume if avg_volume > 0 else 1.0
        if vol_ratio > 1.5 or vol_ratio < 0.5:
            signals.append(
                Signal(
                    source="yfinance",
                    signal_type=SignalType.VOLUME,
                    ticker=ticker_symbol,
                    headline=f"{ticker_symbol} volume {vol_ratio:.1f}x average",
                    sentiment=0.1 if vol_ratio > 1.5 else -0.1,
                    magnitude=min(1.0, abs(vol_ratio - 1.0) / 2),
                    metadata={"volume": float(latest["Volume"]), "avg_volume": float(avg_volume)},
                )
            )

        # Simple moving average crossover signal
        if len(hist) >= 20:
            sma5 = hist["Close"].tail(5).mean()
            sma20 = hist["Close"].tail(20).mean()
            cross = (sma5 - sma20) / sma20

            signals.append(
                Signal(
                    source="yfinance",
                    signal_type=SignalType.TECHNICAL,
                    ticker=ticker_symbol,
                    headline=f"{ticker_symbol} SMA5 {'above' if cross > 0 else 'below'} SMA20 by {abs(cross)*100:.1f}%",
                    sentiment=max(-1.0, min(1.0, cross * 5)),
                    magnitude=min(1.0, abs(cross) * 10),
                    metadata={"sma5": float(sma5), "sma20": float(sma20)},
                )
            )

        return signals
