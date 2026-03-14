"""SEC EDGAR filing collector using EFTS full-text search API."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

# SEC EDGAR full-text search API (free, no key needed)
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={start}&enddt={end}&forms=8-K,10-Q,10-K,4"
EDGAR_FILING_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=8-K&dateb=&owner=include&count=5&search_text=&action=getcompany&output=atom"


class SECFilingCollector(BaseCollector):
    """Collects signals from recent SEC EDGAR filings via EFTS search API."""

    @property
    def name(self) -> str:
        return "sec_edgar"

    def collect(self, tickers: list[str]) -> list[Signal]:
        signals = []
        for ticker in tickers:
            try:
                signals.extend(self._collect_ticker(ticker))
            except Exception as e:
                logger.debug(f"SEC EDGAR failed for {ticker}: {e}")
        return signals

    def _collect_ticker(self, ticker: str) -> list[Signal]:
        """Query EDGAR EFTS for recent filings mentioning this ticker."""
        signals = []

        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=7)

        url = EDGAR_SEARCH_URL.format(
            ticker=ticker,
            start=start_date.isoformat(),
            end=end_date.isoformat(),
        )

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Finn Financial Agent finn@example.com",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            logger.debug(f"EDGAR API request failed for {ticker}: {e}")
            return signals

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return signals

        for hit in hits[:3]:  # Max 3 filings per ticker
            source = hit.get("_source", {})
            form_type = source.get("form_type", "")
            filed_date = source.get("file_date", "")
            entity = source.get("entity_name", ticker)
            description = source.get("file_description", "")

            # Filing type determines sentiment signal
            # 8-K = material events (could be good or bad, signal is magnitude)
            # 10-Q/10-K = quarterly/annual (routine but notable)
            # 4 = insider trading (directional signal)
            if form_type == "4":
                headline = f"{ticker} insider transaction filed ({filed_date})"
                sentiment = 0.1  # Slight positive bias — insiders buying
                magnitude = 0.4
            elif form_type == "8-K":
                headline = f"{ticker} filed 8-K: {description[:80] or 'material event'} ({filed_date})"
                sentiment = 0.0  # Neutral — could go either way
                magnitude = 0.6  # But high magnitude — material events matter
            else:
                headline = f"{ticker} filed {form_type} ({filed_date})"
                sentiment = 0.0
                magnitude = 0.3

            signals.append(
                Signal(
                    source="sec_edgar",
                    signal_type=SignalType.FILING,
                    ticker=ticker,
                    headline=headline,
                    content=f"Entity: {entity}. Form: {form_type}. Filed: {filed_date}. {description[:200]}",
                    sentiment=sentiment,
                    magnitude=magnitude,
                    metadata={
                        "form_type": form_type,
                        "file_date": filed_date,
                        "entity_name": entity,
                    },
                )
            )

        return signals
