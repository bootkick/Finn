"""Crypto market data collector using yfinance and CoinGecko."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

# Top crypto tickers (yfinance format: add -USD suffix)
CRYPTO_COINS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "ADA": "ADA-USD",
    "DOT": "DOT-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "MATIC": "MATIC-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
}

# CoinGecko IDs for free API (no key needed)
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "XRP": "ripple",
    "DOGE": "dogecoin",
}


class CryptoCollector(BaseCollector):
    """Collects price, volume, and trend signals for major crypto coins."""

    @property
    def name(self) -> str:
        return "crypto"

    def collect(self, tickers: list[str]) -> list[Signal]:
        signals = []

        # Collect via yfinance (price/volume/technicals)
        signals.extend(self._collect_yfinance(tickers))

        # Collect via CoinGecko (trending, market cap, community)
        signals.extend(self._collect_coingecko(tickers))

        return signals

    def _collect_yfinance(self, tickers: list[str]) -> list[Signal]:
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed, skipping crypto price data")
            return []

        signals = []
        # Filter to only crypto tickers in our list
        crypto_tickers = [t for t in tickers if t in CRYPTO_COINS]

        for coin in crypto_tickers:
            try:
                yf_ticker = CRYPTO_COINS[coin]
                ticker = yf.Ticker(yf_ticker)
                hist = ticker.history(period="1mo")

                if hist.empty:
                    continue

                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else latest

                # 24h price change
                price_change = (latest["Close"] - prev["Close"]) / prev["Close"]
                signals.append(
                    Signal(
                        source="crypto_yfinance",
                        signal_type=SignalType.PRICE,
                        ticker=coin,
                        headline=f"{coin} {'up' if price_change > 0 else 'down'} {abs(price_change)*100:.1f}%",
                        sentiment=max(-1.0, min(1.0, price_change * 5)),
                        magnitude=min(1.0, abs(price_change) * 3),
                        metadata={
                            "close": float(latest["Close"]),
                            "prev_close": float(prev["Close"]),
                            "change_pct": float(price_change),
                            "asset_type": "crypto",
                        },
                    )
                )

                # Volume spike
                avg_volume = hist["Volume"].mean()
                if avg_volume > 0:
                    vol_ratio = latest["Volume"] / avg_volume
                    if vol_ratio > 2.0 or vol_ratio < 0.3:
                        signals.append(
                            Signal(
                                source="crypto_yfinance",
                                signal_type=SignalType.VOLUME,
                                ticker=coin,
                                headline=f"{coin} volume {vol_ratio:.1f}x average — {'whale activity?' if vol_ratio > 3 else 'unusual'}",
                                sentiment=0.2 if vol_ratio > 2.0 else -0.2,
                                magnitude=min(1.0, abs(vol_ratio - 1.0) / 3),
                                metadata={"volume_ratio": float(vol_ratio), "asset_type": "crypto"},
                            )
                        )

                # 7-day momentum
                if len(hist) >= 7:
                    week_ago = hist["Close"].iloc[-7]
                    week_change = (latest["Close"] - week_ago) / week_ago
                    signals.append(
                        Signal(
                            source="crypto_yfinance",
                            signal_type=SignalType.TECHNICAL,
                            ticker=coin,
                            headline=f"{coin} 7d momentum: {week_change*100:+.1f}%",
                            sentiment=max(-1.0, min(1.0, week_change * 3)),
                            magnitude=min(1.0, abs(week_change) * 2),
                            metadata={"week_change": float(week_change), "asset_type": "crypto"},
                        )
                    )

            except Exception as e:
                logger.debug(f"Failed crypto data for {coin}: {e}")

        return signals

    def _collect_coingecko(self, tickers: list[str]) -> list[Signal]:
        """Collect trending/community signals from CoinGecko free API."""
        signals = []

        # Check trending coins
        try:
            req = urllib.request.Request(
                "https://api.coingecko.com/api/v3/search/trending",
                headers={"Accept": "application/json", "User-Agent": "Finn/0.1"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            trending_ids = set()
            for item in data.get("coins", []):
                coin_data = item.get("item", {})
                coin_id = coin_data.get("id", "")
                trending_ids.add(coin_id)

                # Find matching ticker
                for symbol, cg_id in COINGECKO_IDS.items():
                    if cg_id == coin_id and symbol in tickers:
                        rank = coin_data.get("market_cap_rank", 0)
                        signals.append(
                            Signal(
                                source="coingecko",
                                signal_type=SignalType.SOCIAL,
                                ticker=symbol,
                                headline=f"{symbol} is TRENDING on CoinGecko (rank #{rank})",
                                sentiment=0.6,
                                magnitude=0.7,
                                metadata={
                                    "trending": True,
                                    "market_cap_rank": rank,
                                    "asset_type": "crypto",
                                },
                            )
                        )

        except Exception as e:
            logger.debug(f"CoinGecko trending check failed: {e}")

        return signals
