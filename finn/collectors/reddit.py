"""Reddit sentiment collector using PRAW."""

from __future__ import annotations

import logging

from finn.collectors.base import BaseCollector
from finn.models.signals import Signal, SignalType

logger = logging.getLogger(__name__)

SUBREDDITS = ["wallstreetbets", "stocks", "investing"]


class RedditCollector(BaseCollector):
    """Collects social sentiment from Reddit financial subreddits."""

    def __init__(self, client_id: str = "", client_secret: str = "", user_agent: str = ""):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

    @property
    def name(self) -> str:
        return "reddit"

    @property
    def is_available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def collect(self, tickers: list[str]) -> list[Signal]:
        if not self.is_available:
            logger.info("Reddit API keys not configured, skipping")
            return []

        try:
            import praw
        except ImportError:
            logger.warning("praw not installed, skipping Reddit")
            return []

        signals = []
        try:
            reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
            ticker_set = {t.upper() for t in tickers}

            for sub_name in SUBREDDITS:
                try:
                    signals.extend(
                        self._collect_subreddit(reddit, sub_name, ticker_set)
                    )
                except Exception as e:
                    logger.warning(f"Failed to collect from r/{sub_name}: {e}")
        except Exception as e:
            logger.warning(f"Reddit connection failed: {e}")

        return signals

    def _collect_subreddit(self, reddit, sub_name: str, tickers: set[str]) -> list[Signal]:
        signals = []
        subreddit = reddit.subreddit(sub_name)

        for post in subreddit.hot(limit=25):
            title = post.title
            text = f"{title} {post.selftext[:500] if post.selftext else ''}"

            # Find mentioned tickers
            mentioned = self._find_tickers(text, tickers)
            if not mentioned:
                continue

            # Engagement as signal strength
            score = post.score
            magnitude = min(1.0, score / 1000)  # Normalize: 1000 upvotes = max magnitude

            # Upvote ratio as rough sentiment
            sentiment = (post.upvote_ratio - 0.5) * 2  # 0.5->0, 0.75->0.5, 1.0->1.0

            for ticker in mentioned:
                signals.append(
                    Signal(
                        source="reddit",
                        signal_type=SignalType.SOCIAL,
                        ticker=ticker,
                        headline=title[:200],
                        content=text[:500],
                        sentiment=sentiment,
                        magnitude=magnitude,
                        metadata={
                            "subreddit": sub_name,
                            "score": score,
                            "upvote_ratio": post.upvote_ratio,
                            "num_comments": post.num_comments,
                        },
                    )
                )
        return signals

    def _find_tickers(self, text: str, tickers: set[str]) -> list[str]:
        """Find which tickers are mentioned in text."""
        words = set(text.upper().replace("$", " ").split())
        return [t for t in tickers if t in words]
