from pathlib import Path

from backend.profile_resolver import load_demo_profiles


def test_readme_lists_cli_usage_and_api_contract():
    text = Path("README.md").read_text()
    assert "CLI" in text
    assert "python -m backend.cli" in text
    assert "/api/profile/resolve" in text
    assert "Agent Handoff" in text
    assert "Copy Instructions" in text


def test_license_exists_and_uses_mit_text():
    text = Path("LICENSE").read_text()
    assert "MIT License" in text
    assert "Permission is hereby granted, free of charge" in text


def test_demo_profiles_exist_in_repo_and_include_openai_profile():
    text = Path("DEMO-PROFILES.md").read_text()
    assert "## 1. OpenAI" in text
    assert "## 2. Northvolt" in text


def test_demo_profiles_markdown_matches_parser_contract():
    text = Path("DEMO-PROFILES.md").read_text()
    assert "**Description:**" in text
    assert "**Expected matches:**" in text

    profiles = load_demo_profiles(Path("DEMO-PROFILES.md"))

    assert profiles["openai"][0] == "OpenAI"
    assert profiles["northvolt"][0] == "Northvolt"
    assert profiles["doctolib"][0] == "Doctolib"


def test_env_example_mentions_seed_snapshot_override():
    text = Path(".env.example").read_text()
    assert "INDEX_SEED_SNAPSHOT_PATH=" in text
