"""Signal collectors for Finn."""

from finn.collectors.base import BaseCollector
from finn.collectors.market_data import MarketDataCollector
from finn.collectors.news import NewsCollector
from finn.collectors.reddit import RedditCollector
from finn.collectors.sec_filings import SECFilingCollector
from finn.collectors.crypto import CryptoCollector
from finn.collectors.web_news import WebNewsCollector

__all__ = [
    "BaseCollector",
    "MarketDataCollector",
    "NewsCollector",
    "RedditCollector",
    "SECFilingCollector",
    "CryptoCollector",
    "WebNewsCollector",
]
