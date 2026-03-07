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

    # Agent settings
    watchlist: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,JNJ,WMT,PG,UNH,HD,MA"
    data_dir: str = "./data"
    log_level: str = "INFO"
    evolution_min_days: int = 7
    max_picks_per_day: int = 5

    @property
    def watchlist_tickers(self) -> list[str]:
        return [t.strip() for t in self.watchlist.split(",") if t.strip()]

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


def get_settings() -> Settings:
    return Settings()
