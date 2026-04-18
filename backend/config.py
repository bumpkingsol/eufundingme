from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OPENAI_TEXT_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
SENTRY_RELEASE_CI_ENV_VARS = (
    "GITHUB_SHA",
    "VERCEL_GIT_COMMIT_SHA",
    "RENDER_GIT_COMMIT",
)
DOTENV_FILENAMES = (".env", ".env.local")
CONFIG_ROOT = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    openai_api_key: str | None = None
    openai_match_model: str = DEFAULT_OPENAI_TEXT_MODEL
    openai_profile_expansion_model: str = DEFAULT_OPENAI_TEXT_MODEL
    openai_embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL
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
    index_seed_snapshot_path: str = ""
    index_snapshot_max_age_hours: int = 24
    index_refresh_stall_seconds: int = 60


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _load_dotenv_values() -> dict[str, str]:
    loaded: dict[str, str] = {}
    for filename in DOTENV_FILENAMES:
        loaded.update(_parse_dotenv_file(CONFIG_ROOT / filename))
    return loaded


def _env(name: str, default: str | None = None, *, dotenv_values: dict[str, str]) -> str | None:
    return os.getenv(name, dotenv_values.get(name, default))


def _discover_git_commit_sha() -> str | None:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    commit_sha = completed.stdout.strip()
    return commit_sha or None


def _resolve_sentry_release(*, dotenv_values: dict[str, str]) -> str | None:
    explicit_release = _env("SENTRY_RELEASE", dotenv_values=dotenv_values)
    if explicit_release:
        return explicit_release

    for env_var in SENTRY_RELEASE_CI_ENV_VARS:
        commit_sha = _env(env_var, dotenv_values=dotenv_values)
        if commit_sha:
            return commit_sha

    return _discover_git_commit_sha()


def load_settings() -> Settings:
    dotenv_values = _load_dotenv_values()
    raw_max_pages = _env("EC_MAX_PAGES_PER_PREFIX", dotenv_values=dotenv_values)
    default_snapshot_path = Path(__file__).resolve().parent.parent / ".cache" / "grant-index.json"
    default_seed_snapshot_path = Path(__file__).resolve().parent / "data" / "grant-index.seed.json"
    return Settings(
        host=_env("HOST", "127.0.0.1", dotenv_values=dotenv_values) or "127.0.0.1",
        port=int(_env("PORT", "8000", dotenv_values=dotenv_values) or "8000"),
        openai_api_key=_env("OPENAI_API_KEY", dotenv_values=dotenv_values),
        openai_match_model=_env("OPENAI_MATCH_MODEL", DEFAULT_OPENAI_TEXT_MODEL, dotenv_values=dotenv_values)
        or DEFAULT_OPENAI_TEXT_MODEL,
        openai_profile_expansion_model=_env(
            "OPENAI_PROFILE_EXPANSION_MODEL",
            DEFAULT_OPENAI_TEXT_MODEL,
            dotenv_values=dotenv_values,
        )
        or DEFAULT_OPENAI_TEXT_MODEL,
        openai_embedding_model=_env(
            "OPENAI_EMBEDDING_MODEL",
            DEFAULT_OPENAI_EMBEDDING_MODEL,
            dotenv_values=dotenv_values,
        )
        or DEFAULT_OPENAI_EMBEDDING_MODEL,
        openai_timeout_seconds=float(_env("OPENAI_TIMEOUT_SECONDS", "30", dotenv_values=dotenv_values) or "30"),
        openai_max_retries=int(_env("OPENAI_MAX_RETRIES", "2", dotenv_values=dotenv_values) or "2"),
        openai_match_reasoning_effort=_env("OPENAI_MATCH_REASONING_EFFORT", "low", dotenv_values=dotenv_values)
        or "low",
        openai_profile_reasoning_effort=_env(
            "OPENAI_PROFILE_REASONING_EFFORT",
            "none",
            dotenv_values=dotenv_values,
        )
        or "none",
        sentry_dsn=_env("SENTRY_DSN", dotenv_values=dotenv_values),
        sentry_environment=_env("SENTRY_ENVIRONMENT", "development", dotenv_values=dotenv_values) or "development",
        sentry_release=_resolve_sentry_release(dotenv_values=dotenv_values),
        sentry_send_default_pii=(
            _env("SENTRY_SEND_DEFAULT_PII", "false", dotenv_values=dotenv_values) or "false"
        ).lower()
        == "true",
        ec_page_size=int(_env("EC_PAGE_SIZE", "100", dotenv_values=dotenv_values) or "100"),
        ec_max_pages_per_prefix=int(raw_max_pages) if raw_max_pages else None,
        shortlist_limit=int(_env("SHORTLIST_LIMIT", "10", dotenv_values=dotenv_values) or "10"),
        ec_timeout_seconds=float(_env("EC_TIMEOUT_SECONDS", "30", dotenv_values=dotenv_values) or "30"),
        ec_max_retries=int(_env("EC_MAX_RETRIES", "2", dotenv_values=dotenv_values) or "2"),
        ec_retry_backoff_seconds=float(
            _env("EC_RETRY_BACKOFF_SECONDS", "0.5", dotenv_values=dotenv_values) or "0.5"
        ),
        sentry_traces_sample_rate=float(
            _env("SENTRY_TRACES_SAMPLE_RATE", "0.2", dotenv_values=dotenv_values) or "0.2"
        ),
        cli_match_timeout_seconds=int(
            _env(
                "CLI_MATCH_TIMEOUT_SECONDS",
                _env("EUI_MATCH_TIMEOUT_SECONDS", "60", dotenv_values=dotenv_values) or "60",
                dotenv_values=dotenv_values,
            )
            or "60"
        ),
        index_snapshot_path=_env("INDEX_SNAPSHOT_PATH", str(default_snapshot_path), dotenv_values=dotenv_values)
        or str(default_snapshot_path),
        index_seed_snapshot_path=_env(
            "INDEX_SEED_SNAPSHOT_PATH",
            str(default_seed_snapshot_path),
            dotenv_values=dotenv_values,
        )
        or str(default_seed_snapshot_path),
        index_snapshot_max_age_hours=int(
            _env("INDEX_SNAPSHOT_MAX_AGE_HOURS", "24", dotenv_values=dotenv_values) or "24"
        ),
        index_refresh_stall_seconds=int(
            _env("INDEX_REFRESH_STALL_SECONDS", "60", dotenv_values=dotenv_values) or "60"
        ),
    )
