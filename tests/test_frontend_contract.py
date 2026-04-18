from pathlib import Path


def test_frontend_mentions_cli():
    html = Path("frontend/index.html").read_text()
    assert "CLI" in html
    assert "python -m backend.cli" in html
