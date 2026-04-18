from pathlib import Path


def test_frontend_mentions_cli():
    html = Path("frontend/index.html").read_text()
    assert "CLI" in html
    assert "python -m backend.cli" in html
    assert "Agent Handoff" in html
    assert 'id="agent-handoff-copy"' in html
    assert 'id="agent-handoff-instructions"' in html
    assert "request_id" in html


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


def test_frontend_keeps_try_openai_button_on_one_line():
    css = Path("frontend/styles.css").read_text()
    assert ".secondary-button" in css
    assert ".secondary-button {\n  padding: 0.7rem 1rem;\n  background: rgba(255, 252, 247, 0.88);\n  color: var(--ink);\n  border: 1px solid rgba(29, 27, 24, 0.12);\n  box-shadow: none;\n  white-space: nowrap;" in css
