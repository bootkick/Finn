"""Crypto market data collector using Yahoo Finance HTTP API and CoinGecko."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.collectors.market_data import _yahoo_request, YAHOO_CHART_URL
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

        # Collect via Yahoo Finance HTTP API (price/volume/technicals)
        signals.extend(self._collect_yahoo(tickers))

        # Collect via CoinGecko (trending, market cap, community)
        signals.extend(self._collect_coingecko(tickers))

        return signals

    def _collect_yahoo(self, tickers: list[str]) -> list[Signal]:
        """Collect crypto price data from Yahoo Finance HTTP API."""
        signals = []
        crypto_tickers = [t for t in tickers if t in CRYPTO_COINS]

        for coin in crypto_tickers:
            try:
                yf_symbol = CRYPTO_COINS[coin]
                url = YAHOO_CHART_URL.format(symbol=yf_symbol)
                data = _yahoo_request(url)

                result = data.get("chart", {}).get("result", [])
                if not result:
                    continue

                chart = result[0]
                quotes = chart.get("indicators", {}).get("quote", [{}])[0]
                timestamps = chart.get("timestamp", [])
                closes = quotes.get("close", [])
                volumes = quotes.get("volume", [])

                valid_closes = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
                valid_volumes = [v for v in volumes if v is not None]

                if len(valid_closes) < 2:
                    continue

                latest_price = valid_closes[-1][1]
                prev_price = valid_closes[-2][1]

                # 24h price change
                price_change = (latest_price - prev_price) / prev_price
                signals.append(
                    Signal(
                        source="crypto_yahoo",
                        signal_type=SignalType.PRICE,
                        ticker=coin,
                        headline=f"{coin} {'up' if price_change > 0 else 'down'} {abs(price_change)*100:.1f}%",
                        sentiment=max(-1.0, min(1.0, price_change * 5)),
                        magnitude=min(1.0, abs(price_change) * 3),
                        metadata={
                            "close": float(latest_price),
                            "prev_close": float(prev_price),
                            "change_pct": float(price_change),
                            "asset_type": "crypto",
                        },
                    )
                )

                # Volume spike
                if valid_volumes:
                    avg_volume = sum(valid_volumes) / len(valid_volumes)
                    if avg_volume > 0:
                        vol_ratio = valid_volumes[-1] / avg_volume
                        if vol_ratio > 2.0 or vol_ratio < 0.3:
                            signals.append(
                                Signal(
                                    source="crypto_yahoo",
                                    signal_type=SignalType.VOLUME,
                                    ticker=coin,
                                    headline=f"{coin} volume {vol_ratio:.1f}x average — {'whale activity?' if vol_ratio > 3 else 'unusual'}",
                                    sentiment=0.2 if vol_ratio > 2.0 else -0.2,
                                    magnitude=min(1.0, abs(vol_ratio - 1.0) / 3),
                                    metadata={"volume_ratio": float(vol_ratio), "asset_type": "crypto"},
                                )
                            )

                # 7-day momentum
                close_values = [c for _, c in valid_closes]
                if len(close_values) >= 7:
                    week_ago = close_values[-7]
                    week_change = (latest_price - week_ago) / week_ago
                    signals.append(
                        Signal(
                            source="crypto_yahoo",
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

        try:
            req = urllib.request.Request(
                "https://api.coingecko.com/api/v3/search/trending",
                headers={"Accept": "application/json", "User-Agent": "Finn/0.1"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            for item in data.get("coins", []):
                coin_data = item.get("item", {})
                coin_id = coin_data.get("id", "")

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
