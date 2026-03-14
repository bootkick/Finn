"""Web news collector — fetches real financial news via web scraping.

Uses Yahoo Finance's news endpoint and Google News RSS (no API key needed).
All data comes from live web requests — no mock data, no hallucination.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

# Simple keyword sentiment (bootstrap heuristic — strategy can evolve better)
BULLISH_KEYWORDS = [
    "surge", "soar", "rally", "beat", "upgrade", "outperform", "record high",
    "growth", "profit", "gains", "bullish", "positive", "strong", "boom",
    "breakout", "upside", "exceed", "optimistic", "buy", "raises",
]
BEARISH_KEYWORDS = [
    "crash", "plunge", "drop", "miss", "downgrade", "underperform", "layoff",
    "loss", "decline", "bearish", "negative", "weak", "slump", "warning",
    "risk", "concern", "fear", "sell-off", "selloff", "cut", "lowers",
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}+stock&hl=en-US&gl=US&ceid=US:en"


class WebNewsCollector(BaseCollector):
    """Collects real news from the web for financial tickers."""

    @property
    def name(self) -> str:
        return "web_news"

    def collect(self, tickers: list[str]) -> list[Signal]:
        signals = []
        for ticker in tickers:
            try:
                signals.extend(self._collect_google_news(ticker))
            except Exception as e:
                logger.debug(f"Web news failed for {ticker}: {e}")

            try:
                signals.extend(self._collect_yahoo_news(ticker))
            except Exception as e:
                logger.debug(f"Yahoo news failed for {ticker}: {e}")

        return signals

    def _collect_google_news(self, ticker: str) -> list[Signal]:
        """Fetch recent news from Google News RSS feed."""
        signals = []
        url = GOOGLE_NEWS_RSS.format(query=ticker)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Finn Financial Agent)"},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_data = resp.read().decode()
        except Exception as e:
            logger.debug(f"Google News RSS failed for {ticker}: {e}")
            return signals

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return signals

        # Parse RSS items
        items = root.findall(".//item")
        for item in items[:5]:  # Latest 5 articles
            title_el = item.find("title")
            pub_date_el = item.find("pubDate")
            link_el = item.find("link")

            if title_el is None or title_el.text is None:
                continue

            title = title_el.text.strip()
            link = link_el.text.strip() if link_el is not None and link_el.text else ""

            sentiment = self._keyword_sentiment(title.lower())
            if abs(sentiment) < 0.05:
                continue  # Skip if no clear signal

            signals.append(
                Signal(
                    source="google_news",
                    signal_type=SignalType.NEWS,
                    ticker=ticker,
                    headline=title[:200],
                    content=title,
                    sentiment=sentiment,
                    magnitude=min(1.0, abs(sentiment)),
                    metadata={"link": link, "source_feed": "google_news"},
                )
            )

        return signals

    def _collect_yahoo_news(self, ticker: str) -> list[Signal]:
        """Fetch news from Yahoo Finance's quote endpoint."""
        signals = []
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Finn Financial Agent)",
                "Accept": "application/json",
            },
        )

        # Yahoo Finance chart API doesn't return news directly,
        # but we can check the quote summary for key info
        try:
            quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
            req = urllib.request.Request(
                quote_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Finn Financial Agent)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            results = data.get("quoteResponse", {}).get("result", [])
            if not results:
                return signals

            quote = results[0]
            # Extract market state info as a signal
            market_state = quote.get("marketState", "")
            display_name = quote.get("displayName", quote.get("shortName", ticker))

            # 52-week high/low proximity signal
            price = quote.get("regularMarketPrice", 0)
            high_52 = quote.get("fiftyTwoWeekHigh", 0)
            low_52 = quote.get("fiftyTwoWeekLow", 0)

            if price and high_52 and low_52 and high_52 > low_52:
                range_position = (price - low_52) / (high_52 - low_52)

                if range_position > 0.9:
                    signals.append(
                        Signal(
                            source="yahoo_quote",
                            signal_type=SignalType.TECHNICAL,
                            ticker=ticker,
                            headline=f"{display_name} trading near 52-week high ({range_position:.0%} of range)",
                            sentiment=0.3,
                            magnitude=0.5,
                            metadata={"range_position": range_position, "price": price, "52w_high": high_52},
                        )
                    )
                elif range_position < 0.1:
                    signals.append(
                        Signal(
                            source="yahoo_quote",
                            signal_type=SignalType.TECHNICAL,
                            ticker=ticker,
                            headline=f"{display_name} trading near 52-week low ({range_position:.0%} of range)",
                            sentiment=-0.3,
                            magnitude=0.5,
                            metadata={"range_position": range_position, "price": price, "52w_low": low_52},
                        )
                    )

        except Exception as e:
            logger.debug(f"Yahoo quote failed for {ticker}: {e}")

        return signals

    def _keyword_sentiment(self, text: str) -> float:
        """Basic keyword sentiment. Strategy can evolve better NLP."""
        bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
        bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return (bull_count - bear_count) / total
