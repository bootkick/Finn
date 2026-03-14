"""Configuration for Finn agent."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_prefix": "FINN_", "env_file": ".env", "extra": "ignore"}

    # API Keys (no prefix — standard env var names)
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    reddit_client_id: str = Field(default="", alias="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", alias="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(
        default="finn-financial-agent/0.1", alias="REDDIT_USER_AGENT"
    )
    news_api_key: str = Field(default="", alias="NEWS_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")

    # Trading API (Alpaca)
    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_api_secret: str = Field(default="", alias="ALPACA_API_SECRET")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")

    # Agent settings
    watchlist: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,JNJ,WMT,PG,UNH,HD,MA"
    crypto_watchlist: str = "BTC,ETH,SOL,ADA,XRP,AVAX,LINK,DOGE"
    data_dir: str = "./data"
    log_level: str = "INFO"
    evolution_min_days: int = 7
    max_picks_per_day: int = 5
    enable_trading: bool = False
    enable_crypto: bool = True

    @property
    def watchlist_tickers(self) -> list[str]:
        return [t.strip() for t in self.watchlist.split(",") if t.strip()]

    @property
    def crypto_tickers(self) -> list[str]:
        return [t.strip() for t in self.crypto_watchlist.split(",") if t.strip()]

    @property
    def all_tickers(self) -> list[str]:
        """Combined stock + crypto watchlist."""
        tickers = self.watchlist_tickers
        if self.enable_crypto:
            tickers = tickers + self.crypto_tickers
        return tickers

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        db_dir = self.data_path / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir / "finn.sqlite"

    @property
    def strategies_path(self) -> Path:
        p = self.data_path / "strategies"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def journal_path(self) -> Path:
        p = self.data_path / "journal"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_reddit_keys(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @property
    def has_alpaca_keys(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_api_secret)

    @property
    def memory_path(self) -> Path:
        p = self.data_path / "memory"
        p.mkdir(parents=True, exist_ok=True)
        return p


def get_settings() -> Settings:
    return Settings()
