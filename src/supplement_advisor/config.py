"""Local deployment settings. Secret values must never be returned by the API."""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://advisor:advisor_dev@127.0.0.1:55432/advisor", repr=False
    )
    redis_url: str = Field(default="redis://127.0.0.1:56379/0", repr=False)
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5.6-luna"
    food_safety_api_key: str | None = Field(default=None, repr=False)
    tavily_api_key: str | None = Field(default=None, repr=False)
    clerk_secret_key: str | None = Field(default=None, repr=False)
    langsmith_api_key: str | None = Field(default=None, repr=False)
    external_timeout_seconds: float = Field(default=15, gt=0, le=15)
    model_timeout_seconds: float = Field(default=30, gt=0, le=30)
    analysis_timeout_seconds: int = Field(default=180, ge=1, le=180)
    attempt_timeout_seconds: int = Field(default=60, ge=2, le=60)
    max_tool_calls: int = Field(default=20, ge=1, le=20)
    raw_storage_dir: Path = Path("work/raw")
    frontend_origin: str = "http://localhost:5173"


def configure_logging() -> None:
    # SDK request logs may include source queries or FoodSafety's path-based key.
    for name in ("httpx", "httpcore", "httpcore2", "httpx2", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)


@lru_cache
def get_settings() -> Settings:
    return Settings()
