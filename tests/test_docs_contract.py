from pathlib import Path


def test_readme_lists_cli_usage_and_api_contract():
    text = Path("README.md").read_text()
    assert "CLI" in text
    assert "python -m backend.cli" in text
    assert "/api/profile/resolve" in text


def test_license_exists_and_uses_mit_text():
    text = Path("LICENSE").read_text()
    assert "MIT License" in text
    assert "Permission is hereby granted, free of charge" in text
