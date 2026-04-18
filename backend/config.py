from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    openai_api_key: str | None = None
    openai_match_model: str = "gpt-4o-2024-08-06"
    openai_embedding_model: str = "text-embedding-3-large"
    sentry_dsn: str | None = None
    ec_page_size: int = 100
    ec_max_pages_per_prefix: int | None = None
    shortlist_limit: int = 10
    ec_timeout_seconds: float = 30.0
    ec_max_retries: int = 2
    ec_retry_backoff_seconds: float = 0.5
    sentry_traces_sample_rate: float = 0.2


def load_settings() -> Settings:
    raw_max_pages = os.getenv("EC_MAX_PAGES_PER_PREFIX")
    return Settings(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_match_model=os.getenv("OPENAI_MATCH_MODEL", "gpt-4o-2024-08-06"),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        sentry_dsn=os.getenv("SENTRY_DSN"),
        ec_page_size=int(os.getenv("EC_PAGE_SIZE", "100")),
        ec_max_pages_per_prefix=int(raw_max_pages) if raw_max_pages else None,
        shortlist_limit=int(os.getenv("SHORTLIST_LIMIT", "10")),
        ec_timeout_seconds=float(os.getenv("EC_TIMEOUT_SECONDS", "30")),
        ec_max_retries=int(os.getenv("EC_MAX_RETRIES", "2")),
        ec_retry_backoff_seconds=float(os.getenv("EC_RETRY_BACKOFF_SECONDS", "0.5")),
        sentry_traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
    )
