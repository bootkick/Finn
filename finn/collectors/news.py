"""News collector using RSS feeds."""

from __future__ import annotations

import logging
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

# Financial news RSS feeds (no API key needed)
RSS_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US",
    "https://www.investing.com/rss/news.rss",
]

# Simple keyword-based sentiment (bootstrap until strategy evolves its own)
BULLISH_KEYWORDS = [
    "surge", "soar", "rally", "beat", "upgrade", "outperform", "record high",
    "growth", "profit", "gains", "bullish", "positive", "strong", "boom",
    "breakout", "upside", "exceed", "optimistic",
]
BEARISH_KEYWORDS = [
    "crash", "plunge", "drop", "miss", "downgrade", "underperform", "layoff",
    "loss", "decline", "bearish", "negative", "weak", "slump", "warning",
    "risk", "concern", "fear", "sell-off",
]


class NewsCollector(BaseCollector):
    """Collects news signals from RSS feeds."""

    @property
    def name(self) -> str:
        return "rss_news"

    def collect(self, tickers: list[str]) -> list[Signal]:
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser not installed, skipping news")
            return []

        signals = []
        for ticker in tickers:
            try:
                signals.extend(self._collect_ticker_news(feedparser, ticker))
            except Exception as e:
                logger.warning(f"Failed to collect news for {ticker}: {e}")
        return signals

    def _collect_ticker_news(self, feedparser, ticker: str) -> list[Signal]:
        signals = []
        url = RSS_FEEDS[0].format(ticker=ticker)

        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.debug(f"RSS parse failed for {ticker}: {e}")
            return signals

        for entry in feed.entries[:5]:  # Latest 5 articles per ticker
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            text = f"{title} {summary}".lower()

            sentiment = self._simple_sentiment(text)
            if abs(sentiment) < 0.05:
                continue  # Skip neutral/irrelevant

            signals.append(
                Signal(
                    source="rss_news",
                    signal_type=SignalType.NEWS,
                    ticker=ticker,
                    headline=title[:200],
                    content=summary[:500],
                    sentiment=sentiment,
                    magnitude=min(1.0, abs(sentiment)),
                    metadata={"link": entry.get("link", "")},
                )
            )
        return signals

    def _simple_sentiment(self, text: str) -> float:
        """Basic keyword sentiment. The strategy can evolve better NLP."""
        bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text)
        bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text)
        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return (bull_count - bear_count) / total
