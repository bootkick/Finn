"""Day 1 Strategy — Simple Signal Aggregation.

This is the initial, naive strategy. It counts bullish/bearish signals
per ticker, weighs them by magnitude, and ranks by net score.

This file WILL be replaced by the evolution engine. That's the whole point.
"""

from __future__ import annotations

import collections
import statistics

from finn.strategy.base import Strategy
from finn.models.signals import Signal
from finn.models.picks import Pick, Conviction


class SignalAggregationStrategy(Strategy):
    """V1: Rank tickers by weighted signal sentiment."""

    def analyze(self, signals: list[Signal]) -> list[Pick]:
        if not signals:
            return []

        # Aggregate signals per ticker
        ticker_scores: dict[str, list[float]] = collections.defaultdict(list)
        ticker_signals: dict[str, int] = collections.defaultdict(int)
        ticker_headlines: dict[str, list[str]] = collections.defaultdict(list)

        for sig in signals:
            # Weighted score: sentiment * magnitude
            weighted = sig.sentiment * max(sig.magnitude, 0.1)
            ticker_scores[sig.ticker].append(weighted)
            ticker_signals[sig.ticker] += 1
            if sig.headline:
                ticker_headlines[sig.ticker].append(sig.headline)

        # Score each ticker
        scored = []
        for ticker, scores in ticker_scores.items():
            net_score = sum(scores)
            avg_score = statistics.mean(scores)
            signal_count = ticker_signals[ticker]

            # More signals = more confidence
            confidence_boost = min(1.0, signal_count / 10)
            final_score = net_score * (1 + confidence_boost)

            scored.append((ticker, final_score, avg_score, signal_count))

        # Sort by absolute score (strongest conviction first)
        scored.sort(key=lambda x: abs(x[1]), reverse=True)

        # Convert to picks
        picks = []
        for ticker, score, avg, count in scored[:5]:  # Top 5
            if abs(score) < 0.1:
                continue  # Skip weak signals

            direction = "long" if score > 0 else "short"

            if abs(score) > 1.0:
                conviction = Conviction.HIGH
            elif abs(score) > 0.5:
                conviction = Conviction.MEDIUM
            else:
                conviction = Conviction.LOW

            headlines = ticker_headlines.get(ticker, [])
            top_headline = headlines[0] if headlines else "Signal aggregation"

            picks.append(
                Pick(
                    ticker=ticker,
                    conviction=conviction,
                    direction=direction,
                    reasoning=f"Net score {score:.2f} from {count} signals. {top_headline}",
                    signals_used=count,
                )
            )

        return picks

    def describe(self) -> str:
        return (
            "V1 Signal Aggregation: Counts bullish/bearish signals per ticker, "
            "weights by magnitude, boosts confidence by signal count. "
            "Ranks by absolute net score, picks top 5 with score > 0.1. "
            "No sector analysis, no momentum, no correlation — pure signal counting."
        )
