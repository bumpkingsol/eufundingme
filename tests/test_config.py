from pathlib import Path

from backend.config import DEFAULT_OPENAI_TEXT_MODEL, load_settings


def test_load_settings_reads_agent_config_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_PROFILE_EXPANSION_MODEL", "example-profile-model")
    monkeypatch.setenv("CLI_MATCH_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")
    monkeypatch.setenv("OPENAI_MATCH_REASONING_EFFORT", "medium")
    monkeypatch.setenv("OPENAI_PROFILE_REASONING_EFFORT", "low")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
    monkeypatch.setenv("SENTRY_RELEASE", "2026.04.18")
    monkeypatch.setenv("SENTRY_SEND_DEFAULT_PII", "true")

    settings = load_settings()

    assert settings.openai_profile_expansion_model == "example-profile-model"
    assert settings.cli_match_timeout_seconds == 90
    assert settings.openai_timeout_seconds == 45
    assert settings.openai_max_retries == 5
    assert settings.openai_match_reasoning_effort == "medium"
    assert settings.openai_profile_reasoning_effort == "low"
    assert settings.sentry_environment == "staging"
    assert settings.sentry_release == "2026.04.18"
    assert settings.sentry_send_default_pii is True


def test_load_settings_uses_eui_match_timeout_alias(monkeypatch):
    monkeypatch.setenv("EUI_MATCH_TIMEOUT_SECONDS", "45")
    monkeypatch.delenv("CLI_MATCH_TIMEOUT_SECONDS", raising=False)

    settings = load_settings()

    assert settings.cli_match_timeout_seconds == 45


def test_load_settings_uses_hardened_defaults(monkeypatch):
    for key in [
        "OPENAI_MATCH_MODEL",
        "OPENAI_PROFILE_EXPANSION_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
        "OPENAI_MAX_RETRIES",
        "OPENAI_MATCH_REASONING_EFFORT",
        "OPENAI_PROFILE_REASONING_EFFORT",
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_SEND_DEFAULT_PII",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("backend.config._discover_git_commit_sha", lambda: None)

    settings = load_settings()

    assert settings.openai_match_model == DEFAULT_OPENAI_TEXT_MODEL
    assert settings.openai_profile_expansion_model == DEFAULT_OPENAI_TEXT_MODEL
    assert settings.openai_timeout_seconds == 30.0
    assert settings.openai_max_retries == 2
    assert settings.openai_match_reasoning_effort == "low"
    assert settings.openai_profile_reasoning_effort == "none"
    assert settings.sentry_environment == "development"
    assert settings.sentry_release is None
    assert settings.sentry_send_default_pii is False


def test_load_settings_reads_seed_snapshot_override(monkeypatch):
    monkeypatch.setenv("INDEX_SEED_SNAPSHOT_PATH", "/tmp/demo-seed.json")

    settings = load_settings()

    assert settings.index_seed_snapshot_path == "/tmp/demo-seed.json"


def test_load_settings_falls_back_to_git_sha_for_sentry_release(monkeypatch):
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("VERCEL_GIT_COMMIT_SHA", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    monkeypatch.setattr("backend.config._discover_git_commit_sha", lambda: "abc123def456")

    settings = load_settings()

    assert settings.sentry_release == "abc123def456"


def test_load_settings_prefers_ci_commit_sha_over_git_fallback(monkeypatch):
    monkeypatch.delenv("SENTRY_RELEASE", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "feedface1234")
    monkeypatch.setattr("backend.config._discover_git_commit_sha", lambda: "abc123def456")

    settings = load_settings()

    assert settings.sentry_release == "feedface1234"


def test_load_settings_reads_values_from_dotenv_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("OPENAI_MATCH_MODEL", raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "SENTRY_DSN=https://example@sentry.invalid/1",
                "SENTRY_ENVIRONMENT=staging",
                "OPENAI_MATCH_MODEL=dotenv-model",
            ]
        )
    )

    settings = load_settings()

    assert settings.sentry_dsn == "https://example@sentry.invalid/1"
    assert settings.sentry_environment == "staging"
    assert settings.openai_match_model == "dotenv-model"


def test_load_settings_prefers_process_env_and_dotenv_local(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "process-env")
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    (tmp_path / ".env").write_text("SENTRY_DSN=https://env@sentry.invalid/1\nSENTRY_ENVIRONMENT=dotenv-env\n")
    (tmp_path / ".env.local").write_text(
        "SENTRY_DSN=https://local@sentry.invalid/1\nSENTRY_ENVIRONMENT=dotenv-local\n"
    )

    settings = load_settings()

    assert settings.sentry_dsn == "https://local@sentry.invalid/1"
    assert settings.sentry_environment == "process-env"
