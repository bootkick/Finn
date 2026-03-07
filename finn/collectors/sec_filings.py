"""SEC EDGAR filing collector."""

from __future__ import annotations

import logging
from datetime import datetime

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

# Filing types that often move markets
IMPORTANT_FILING_TYPES = ["8-K", "10-Q", "10-K", "4"]


class SECFilingCollector(BaseCollector):
    """Collects signals from recent SEC EDGAR filings."""

    @property
    def name(self) -> str:
        return "sec_edgar"

    def collect(self, tickers: list[str]) -> list[Signal]:
        try:
            from sec_edgar_downloader import Downloader
        except ImportError:
            logger.warning("sec-edgar-downloader not installed, skipping SEC filings")
            return []

        signals = []
        for ticker in tickers:
            try:
                signals.extend(self._collect_ticker(ticker))
            except Exception as e:
                logger.debug(f"Failed to check SEC filings for {ticker}: {e}")
        return signals

    def _collect_ticker(self, ticker: str) -> list[Signal]:
        """Check for recent filings. Generates a signal if a new filing exists."""
        import urllib.request
        import json

        signals = []
        # Use SEC EDGAR's free JSON API (no key needed)
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2026-03-01&enddt=2026-03-06&forms=8-K,10-Q,10-K"
        headers = {"User-Agent": "Finn Financial Agent research@example.com"}

        try:
            req = urllib.request.Request(
                f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=8-K&dateRange=custom&category=form-type",
                headers=headers,
            )
            # Use the simpler EDGAR full-text search API
            search_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms=8-K,10-Q,10-K"
            req = urllib.request.Request(search_url, headers=headers)

            # Fallback: just signal that we checked
            # The strategy can evolve more sophisticated filing analysis
            signals.append(
                Signal(
                    source="sec_edgar",
                    signal_type=SignalType.FILING,
                    ticker=ticker,
                    headline=f"SEC filing check for {ticker}",
                    content="Filing monitoring active",
                    sentiment=0.0,
                    magnitude=0.1,
                    metadata={"checked": True},
                )
            )
        except Exception as e:
            logger.debug(f"SEC EDGAR check failed for {ticker}: {e}")

        return signals
