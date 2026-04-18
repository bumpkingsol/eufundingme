from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    openai_api_key: str | None = None
    openai_match_model: str = "gpt-4o-2024-08-06"
    openai_profile_expansion_model: str = "gpt-4o-2024-08-06"
    openai_embedding_model: str = "text-embedding-3-large"
    sentry_dsn: str | None = None
    ec_page_size: int = 100
    ec_max_pages_per_prefix: int = 1
    shortlist_limit: int = 10
    ec_timeout_seconds: float = 30.0
    sentry_traces_sample_rate: float = 0.2
    cli_match_timeout_seconds: int = 60


def load_settings() -> Settings:
    return Settings(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_match_model=os.getenv("OPENAI_MATCH_MODEL", "gpt-4o-2024-08-06"),
        openai_profile_expansion_model=os.getenv(
            "OPENAI_PROFILE_EXPANSION_MODEL",
            "gpt-4o-2024-08-06",
        ),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        sentry_dsn=os.getenv("SENTRY_DSN"),
        ec_page_size=int(os.getenv("EC_PAGE_SIZE", "100")),
        ec_max_pages_per_prefix=int(os.getenv("EC_MAX_PAGES_PER_PREFIX", "1")),
        shortlist_limit=int(os.getenv("SHORTLIST_LIMIT", "10")),
        ec_timeout_seconds=float(os.getenv("EC_TIMEOUT_SECONDS", "30")),
        sentry_traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
        cli_match_timeout_seconds=int(
            os.getenv("CLI_MATCH_TIMEOUT_SECONDS", os.getenv("EUI_MATCH_TIMEOUT_SECONDS", "60"))
        ),
    )
