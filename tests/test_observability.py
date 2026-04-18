from backend.config import Settings
from backend.observability import bind_request_context, build_traces_sampler, initialize_sentry, scrub_sentry_event


def test_scrub_sentry_event_removes_request_body_and_sensitive_headers():
    event = {
        "request": {
            "data": {"company_description": "secret"},
            "headers": {
                "authorization": "Bearer secret",
                "cookie": "session=secret",
                "x-request-id": "req-123",
            },
        }
    }

    scrubbed = scrub_sentry_event(event, {})

    assert scrubbed["request"]["data"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["authorization"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["cookie"] == "[Filtered]"
    assert scrubbed["request"]["headers"]["x-request-id"] == "req-123"


def test_build_traces_sampler_prioritizes_core_api_routes():
    sampler = build_traces_sampler(default_rate=0.2)

    assert sampler({"transaction_context": {"name": "POST /api/match"}}) == 1.0
    assert sampler({"transaction_context": {"name": "POST /api/profile/resolve"}}) == 1.0
    assert sampler({"transaction_context": {"name": "POST /api/application-brief"}}) == 1.0
    assert sampler({"transaction_context": {"name": "GET /api/health"}}) == 0.2


def test_initialize_sentry_uses_explicit_integrations_and_safe_defaults(monkeypatch):
    captured = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("backend.observability.sentry_sdk.init", fake_init)
    monkeypatch.setattr("backend.observability._SENTRY_INITIALIZED", False)

    initialize_sentry(
        Settings(
            sentry_dsn="https://example@sentry.invalid/1",
            sentry_traces_sample_rate=0.2,
            sentry_environment="production",
            sentry_release="2026.04.18",
            sentry_send_default_pii=False,
        )
    )

    assert captured["dsn"] == "https://example@sentry.invalid/1"
    assert captured["environment"] == "production"
    assert captured["release"] == "2026.04.18"
    assert captured["send_default_pii"] is False
    assert captured["before_send"] is scrub_sentry_event
    integration_names = {type(integration).__name__ for integration in captured["integrations"]}
    assert "FastApiIntegration" in integration_names
    assert "OpenAIIntegration" in integration_names
    assert callable(captured["traces_sampler"])


def test_bind_request_context_sets_request_tags_context_and_user(monkeypatch):
    captured_tags = []
    captured_contexts = []
    captured_users = []

    monkeypatch.setattr(
        "backend.observability.sentry_sdk.set_tag",
        lambda key, value: captured_tags.append((key, value)),
    )
    monkeypatch.setattr(
        "backend.observability.sentry_sdk.set_context",
        lambda key, value: captured_contexts.append((key, value)),
    )
    monkeypatch.setattr(
        "backend.observability.sentry_sdk.set_user",
        lambda value: captured_users.append(value),
    )

    bind_request_context(
        operation="match",
        request_id="req-123",
        model="gpt-5.4-mini-2026-03-17",
    )

    assert ("operation", "match") in captured_tags
    assert ("request_id", "req-123") in captured_tags
    assert ("model", "gpt-5.4-mini-2026-03-17") in captured_tags
    assert captured_contexts == [(
        "request_context",
        {
            "operation": "match",
            "request_id": "req-123",
            "model": "gpt-5.4-mini-2026-03-17",
        },
    )]
    assert captured_users == [{"id": "req-123"}]
