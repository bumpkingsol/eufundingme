from pathlib import Path

import pytest

from backend.profile_resolver import DemoProfileResolver, OpenAICompanyProfileExpander, load_demo_profiles, resolve_demo_profiles_path
from backend.website_profile import (
    WebsiteContent,
    WebsiteProfileService,
    fetch_website_html,
    extract_website_content,
    normalize_website_url,
)


def test_demo_profile_resolver_returns_openai_profile_case_insensitive():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("openai")

    assert resolution.resolved is True
    assert resolution.display_name == "OpenAI"
    assert resolution.source == "demo_profile"
    assert resolution.profile is not None
    assert "large language models" in resolution.profile.lower()


def test_demo_profile_resolver_uses_expander_for_unknown_name():
    class FakeExpander:
        def expand(self, query: str):
            assert query == "Acme Robotics"
            return ("Acme Robotics", "We build robotics systems for industrial automation across Europe.")

    resolver = DemoProfileResolver(expander=FakeExpander())

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is True
    assert resolution.display_name == "Acme Robotics"
    assert resolution.source == "llm_expansion"
    assert resolution.profile == "We build robotics systems for industrial automation across Europe."


def test_demo_profile_resolver_returns_unresolved_without_expander():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is False
    assert resolution.source == "unresolved"
    assert resolution.profile is None
    assert "Add one or two sentences" in resolution.message


def test_demo_profiles_include_expected_demo_presets():
    profiles = load_demo_profiles()

    assert "openai" in profiles
    assert "northvolt" in profiles
    assert "doctolib" in profiles


def test_demo_profiles_uses_explicit_path_override(monkeypatch, tmp_path):
    override_file = tmp_path / "DEMO-PROFILES.md"
    override_file.write_text(
        """
## 1. Acme Demo

**Description:**
A fictional company building practical software tooling.

**Expected matches:**
Grants for digital technology.
"""
    )

    monkeypatch.setenv("DEMO_PROFILES_PATH", str(override_file))

    profiles = load_demo_profiles(resolve_demo_profiles_path())

    assert "acme demo" in profiles


def test_resolve_demo_profiles_path_uses_fallback_when_no_candidates(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_PROFILES_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    def fake_exists(path: Path) -> bool:
        return path == tmp_path / "DEMO-PROFILES.md"

    monkeypatch.setattr("pathlib.Path.exists", fake_exists, raising=False)

    assert resolve_demo_profiles_path() == tmp_path / "DEMO-PROFILES.md"


def test_resolved_query_message_is_stable_when_unresolved():
    resolver = DemoProfileResolver()

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is False
    assert resolution.message == (
        "Could not expand company name automatically. Add one or two sentences about what the company does."
    )


def test_demo_profile_resolver_reports_expander_failures_and_returns_unresolved():
    captured = []

    class FailingExpander:
        def expand(self, query: str):
            raise RuntimeError("profile expansion failed")

    resolver = DemoProfileResolver(
        expander=FailingExpander(),
        on_expander_failure=lambda exc, *, context: captured.append((str(exc), context)),
    )

    resolution = resolver.resolve("Acme Robotics")

    assert resolution.resolved is False
    assert resolution.source == "unresolved"
    assert captured == [(
        "profile expansion failed",
        {
            "query": "Acme Robotics",
            "fallback_used": True,
        },
    )]


def test_openai_company_profile_expander_uses_responses_api():
    class FakeResponses:
        def __init__(self) -> None:
            self.calls = []

        def parse(self, **kwargs):
            self.calls.append(kwargs)
            return type(
                "ParsedResponse",
                (),
                {
                    "output_parsed": type(
                        "ExpandedProfile",
                        (),
                        {
                            "display_name": "Acme Robotics",
                            "profile": "We build robotics systems for industrial automation across Europe.",
                        },
                    )()
                },
            )()

    fake_responses = FakeResponses()
    fake_client = type("FakeClient", (), {"responses": fake_responses})()
    expander = OpenAICompanyProfileExpander(
        api_key="test",
        model="gpt-5.4-mini",
        client=fake_client,
        reasoning_effort="none",
    )

    display_name, profile = expander.expand("Acme Robotics")

    assert display_name == "Acme Robotics"
    assert "industrial automation" in profile
    assert fake_responses.calls[0]["model"] == "gpt-5.4-mini"
    assert fake_responses.calls[0]["reasoning"] == {"effort": "none"}


def test_normalize_website_url_adds_https_to_bare_domain():
    assert normalize_website_url("example.com") == "https://example.com"


def test_normalize_website_url_rejects_blank_input():
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url("   ")


@pytest.mark.parametrize("value", ["/foo", "?a=1", "#frag", "exa mple.com"])
def test_normalize_website_url_rejects_malformed_bare_inputs(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


@pytest.mark.parametrize("value", ["ftp://example.com", "mailto:test@example.com", "file:///tmp/site.html"])
def test_normalize_website_url_rejects_unsupported_schemes(value: str):
    with pytest.raises(ValueError, match="unsupported scheme"):
        normalize_website_url(value)


@pytest.mark.parametrize("value", ["https://exa mple.com", "//exa mple.com/path"])
def test_normalize_website_url_rejects_whitespace_in_host_for_explicit_and_scheme_relative_urls(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


@pytest.mark.parametrize("value", ["https://:80", "http://:443/path", "//:8080/foo"])
def test_normalize_website_url_rejects_hostless_authorities(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


@pytest.mark.parametrize("value", ["https://example.com:99999", "https://example.com:abc"])
def test_normalize_website_url_rejects_invalid_ports(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://-bad.com",
        "https://bad-.com",
        "https://exa_mple.com",
        "https://example..com",
    ],
)
def test_normalize_website_url_rejects_invalid_host_labels(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


@pytest.mark.parametrize("value", ["http://", "https:///foo", "https://?a=1"])
def test_normalize_website_url_rejects_malformed_http_urls_without_host(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


def test_normalize_website_url_preserves_full_https_url():
    assert normalize_website_url("https://example.com/path?q=1") == "https://example.com/path?q=1"


def test_normalize_website_url_accepts_unicode_hostname():
    assert normalize_website_url("https://bücher.de") == "https://bücher.de"


def test_normalize_website_url_preserves_scheme_relative_url():
    assert normalize_website_url("//example.com/path?q=1") == "https://example.com/path?q=1"


@pytest.mark.parametrize("value", ["///foo", "//?a=1"])
def test_normalize_website_url_rejects_malformed_scheme_relative_urls_without_host(value: str):
    with pytest.raises(ValueError, match="website url"):
        normalize_website_url(value)


def test_extract_website_content_returns_title_description_and_visible_text():
    html = """
    <html>
      <head>
        <title>Acme Robotics</title>
        <meta name="description" content="Robotics systems for industrial automation.">
        <style>body { color: red; }</style>
      </head>
      <body>
        <h1>Acme Robotics</h1>
        <p>We build robots for factories.</p>
        <script>window.alert('ignore me');</script>
        <noscript>This should be ignored.</noscript>
      </body>
    </html>
    """

    content = extract_website_content(html)

    assert content.title == "Acme Robotics"
    assert content.meta_description == "Robotics systems for industrial automation."
    assert content.body_text == "Acme Robotics We build robots for factories."


def test_extract_website_content_ignores_valueless_meta_name_attribute():
    html = """
    <html>
      <head>
        <meta name content="Robotics systems for industrial automation.">
      </head>
      <body>
        <p>Visible text.</p>
      </body>
    </html>
    """

    content = extract_website_content(html)

    assert content.meta_description is None
    assert content.body_text == "Visible text."


def test_extract_website_content_uses_visible_fragment_text_without_body_tag():
    html = """
    <div>Visible fragment text.</div>
    <p>More content.</p>
    <script>ignore me</script>
    """

    content = extract_website_content(html)

    assert content.body_text == "Visible fragment text. More content."


def test_extract_website_content_captures_body_text_when_head_is_not_closed():
    html = """
    <html>
      <head>
        <title>Acme Robotics</title>
        <meta name="description" content="Robotics systems for industrial automation.">
      <body>
        <h1>Acme Robotics</h1>
        <p>Visible text.</p>
      </body>
    </html>
    """

    content = extract_website_content(html)

    assert content.title == "Acme Robotics"
    assert content.body_text == "Acme Robotics Visible text."


def test_extract_website_content_treats_first_non_head_content_as_body_when_head_is_unclosed():
    html = """
    <html>
      <head>
        <title>Acme Robotics</title>
      <div>Visible text.</div>
      <p>More content.</p>
    </html>
    """

    content = extract_website_content(html)

    assert content.title == "Acme Robotics"
    assert content.body_text == "Visible text. More content."


def test_fetch_website_html_uses_requests_get_path(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self) -> None:
            self.headers = {"content-type": "text/html; charset=utf-8"}
            self.text = "<html><body>Visible text.</body></html>"

        def raise_for_status(self) -> None:
            captured["status_checked"] = True

    def fake_get(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("backend.website_profile.requests.get", fake_get)

    html = fetch_website_html("https://sentry.io")

    assert html == "<html><body>Visible text.</body></html>"
    assert captured["url"] == "https://sentry.io"
    assert captured["kwargs"]["timeout"] == 10.0
    assert captured["kwargs"]["headers"]["User-Agent"].startswith("Mozilla/5.0")
    assert captured["status_checked"] is True


def test_website_profile_service_fetches_html_extracts_content_and_generates_profile():
    captured: dict[str, object] = {}
    html = """
    <html>
      <head>
        <title>Sentry</title>
        <meta name="description" content="Developer observability for monitoring errors and performance.">
      </head>
      <body>
        <h1>Code breaks. Fix it faster.</h1>
        <p>Sentry helps developers monitor application errors and performance across stacks.</p>
      </body>
    </html>
    """

    def fetch_html(url: str) -> str:
        captured["fetched_url"] = url
        return html

    def generate_profile(url: str, content: WebsiteContent) -> tuple[str, str]:
        captured["generated_url"] = url
        captured["content"] = content
        return (
            "Sentry",
            "Sentry builds developer observability tooling for monitoring errors and performance.",
        )

    service = WebsiteProfileService(fetch_html=fetch_html, generate_profile=generate_profile)

    result = service.resolve("sentry.io")

    assert captured["fetched_url"] == "https://sentry.io"
    assert captured["generated_url"] == "https://sentry.io"
    assert isinstance(captured["content"], WebsiteContent)
    assert captured["content"].title == "Sentry"
    assert captured["content"].meta_description == "Developer observability for monitoring errors and performance."
    assert "Sentry helps developers monitor application errors and performance across stacks." in captured["content"].body_text
    assert result.resolved is True
    assert result.display_name == "Sentry"
    assert result.profile == "Sentry builds developer observability tooling for monitoring errors and performance."
    assert result.source == "website_profile"
    assert result.normalized_url == "https://sentry.io"
    assert result.message is None


@pytest.mark.parametrize(
    ("html", "expected_message"),
    [
        (
            """
            <html>
              <head><title>Sentry</title></head>
              <body>   </body>
            </html>
            """,
            "website content",
        ),
        (
            """
            <html>
              <head><title>Sentry</title></head>
              <body><p>Hello</p></body>
            </html>
            """,
            "website content",
        ),
    ],
)
def test_website_profile_service_rejects_thin_or_empty_extracted_content(html: str, expected_message: str):
    def fetch_html(url: str) -> str:
        assert url == "https://sentry.io"
        return html

    def generate_profile(url: str, content: WebsiteContent) -> tuple[str, str]:
        raise AssertionError("generate_profile should not be called for thin content")

    service = WebsiteProfileService(fetch_html=fetch_html, generate_profile=generate_profile)

    with pytest.raises(ValueError, match=expected_message):
        service.resolve("sentry.io")
