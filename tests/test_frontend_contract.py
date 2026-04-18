from pathlib import Path


def test_frontend_mentions_cli():
    html = Path("frontend/index.html").read_text()
    assert "CLI" in html
    assert "python -m backend.cli" in html


def test_frontend_includes_hackathon_footer_and_favicon():
    html = Path("frontend/index.html").read_text()
    assert 'rel="icon"' in html
    assert "🇪🇺" in html
    assert "Built at Codex x Sentry Hackathon, Vienna, April 18 2026" in html
    assert "https://github.com/bumpkingsol/eufundingme" in html
    assert 'id="resolution-banner"' in html
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert 'id="quick-fill-openai"' in html
