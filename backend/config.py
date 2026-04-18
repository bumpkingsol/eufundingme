from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    openai_api_key: str | None = None
    openai_match_model: str = "gpt-5.4-mini-2026-03-17"
    openai_profile_expansion_model: str = "gpt-5.4-mini-2026-03-17"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_timeout_seconds: float = 30.0
    openai_max_retries: int = 2
    openai_match_reasoning_effort: str = "low"
    openai_profile_reasoning_effort: str = "none"
    sentry_dsn: str | None = None
    sentry_environment: str = "development"
    sentry_release: str | None = None
    sentry_send_default_pii: bool = False
    ec_page_size: int = 100
    ec_max_pages_per_prefix: int | None = None
    shortlist_limit: int = 10
    ec_timeout_seconds: float = 30.0
    ec_max_retries: int = 2
    ec_retry_backoff_seconds: float = 0.5
    sentry_traces_sample_rate: float = 0.2
    cli_match_timeout_seconds: int = 60
    index_snapshot_path: str = ""
    index_snapshot_max_age_hours: int = 24
    index_refresh_stall_seconds: int = 60


def load_settings() -> Settings:
    raw_max_pages = os.getenv("EC_MAX_PAGES_PER_PREFIX")
    default_snapshot_path = Path(__file__).resolve().parent.parent / ".cache" / "grant-index.json"
    return Settings(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_match_model=os.getenv("OPENAI_MATCH_MODEL", "gpt-5.4-mini-2026-03-17"),
        openai_profile_expansion_model=os.getenv(
            "OPENAI_PROFILE_EXPANSION_MODEL",
            "gpt-5.4-mini-2026-03-17",
        ),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
        openai_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
        openai_match_reasoning_effort=os.getenv("OPENAI_MATCH_REASONING_EFFORT", "low"),
        openai_profile_reasoning_effort=os.getenv("OPENAI_PROFILE_REASONING_EFFORT", "none"),
        sentry_dsn=os.getenv("SENTRY_DSN"),
        sentry_environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        sentry_release=os.getenv("SENTRY_RELEASE"),
        sentry_send_default_pii=os.getenv("SENTRY_SEND_DEFAULT_PII", "false").lower() == "true",
        ec_page_size=int(os.getenv("EC_PAGE_SIZE", "100")),
        ec_max_pages_per_prefix=int(raw_max_pages) if raw_max_pages else None,
        shortlist_limit=int(os.getenv("SHORTLIST_LIMIT", "10")),
        ec_timeout_seconds=float(os.getenv("EC_TIMEOUT_SECONDS", "30")),
        ec_max_retries=int(os.getenv("EC_MAX_RETRIES", "2")),
        ec_retry_backoff_seconds=float(os.getenv("EC_RETRY_BACKOFF_SECONDS", "0.5")),
        sentry_traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
        cli_match_timeout_seconds=int(
            os.getenv("CLI_MATCH_TIMEOUT_SECONDS", os.getenv("EUI_MATCH_TIMEOUT_SECONDS", "60"))
        ),
        index_snapshot_path=os.getenv("INDEX_SNAPSHOT_PATH", str(default_snapshot_path)),
        index_snapshot_max_age_hours=int(os.getenv("INDEX_SNAPSHOT_MAX_AGE_HOURS", "24")),
        index_refresh_stall_seconds=int(os.getenv("INDEX_REFRESH_STALL_SECONDS", "60")),
    )
