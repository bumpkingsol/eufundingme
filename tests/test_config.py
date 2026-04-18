from backend.config import load_settings


def test_load_settings_reads_agent_config_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_PROFILE_EXPANSION_MODEL", "example-profile-model")
    monkeypatch.setenv("CLI_MATCH_TIMEOUT_SECONDS", "90")

    settings = load_settings()

    assert settings.openai_profile_expansion_model == "example-profile-model"
    assert settings.cli_match_timeout_seconds == 90


def test_load_settings_uses_eui_match_timeout_alias(monkeypatch):
    monkeypatch.setenv("EUI_MATCH_TIMEOUT_SECONDS", "45")
    monkeypatch.delenv("CLI_MATCH_TIMEOUT_SECONDS", raising=False)

    settings = load_settings()

    assert settings.cli_match_timeout_seconds == 45
