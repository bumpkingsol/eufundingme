from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from backend.app import create_app
from backend.billing_client import BillingServiceError, HttpBillingClient, StubBillingClient
from backend.config import Settings


@dataclass(slots=True)
class _QueuedResponse:
    method: str
    url: str
    json_payload: object | None = None
    status_code: int = 200
    error: Exception | None = None
    json_error: Exception | None = None


class _MockHttpx:
    def __init__(self) -> None:
        self.responses: list[_QueuedResponse] = []
        self.calls: list[dict[str, object]] = []

    def add_response(
        self,
        *,
        method: str,
        url: str,
        json: object | None = None,
        status_code: int = 200,
        error: Exception | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.responses.append(
            _QueuedResponse(
                method=method,
                url=url,
                json_payload=json,
                status_code=status_code,
                error=error,
                json_error=json_error,
            )
        )


@pytest.fixture
def httpx_mock(monkeypatch):
    mock = _MockHttpx()

    def fake_request(self, method, url, **kwargs):
        if not mock.responses:
            raise AssertionError("unexpected billing request")

        expected = mock.responses.pop(0)
        assert method == expected.method
        assert url == expected.url
        mock.calls.append({"method": method, "url": url, **kwargs})

        if expected.error is not None:
            raise expected.error

        class FakeResponse:
            def __init__(self, status_code: int, payload: object, json_error: Exception | None) -> None:
                self.status_code = status_code
                self._payload = payload
                self._json_error = json_error

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise requests.HTTPError(f"status {self.status_code}")

            def json(self) -> object:
                if self._json_error is not None:
                    raise self._json_error
                return self._payload

        return FakeResponse(expected.status_code, expected.json_payload, expected.json_error)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    return mock


def test_http_billing_client_sends_shared_auth_header(httpx_mock):
    client = HttpBillingClient(
        base_url="https://billing.internal",
        shared_token="secret-token",
        timeout_seconds=5.0,
    )

    httpx_mock.add_response(
        method="POST",
        url="https://billing.internal/v1/checkout/guest-unlock",
        json={"checkout_url": "https://checkout.stripe.com/test"},
    )

    payload = client.create_guest_unlock_checkout(
        artifact_id="artifact-1",
        fingerprint="fp-1",
        email="founder@example.com",
    )

    assert payload.checkout_url == "https://checkout.stripe.com/test"
    assert httpx_mock.calls[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert httpx_mock.calls[0]["json"] == {
        "artifact_id": "artifact-1",
        "fingerprint": "fp-1",
        "email": "founder@example.com",
    }


@pytest.mark.parametrize(
    ("method_name", "payload", "expected"),
    [
        (
            "create_subscription_checkout",
            {"checkout_url": "https://checkout.stripe.com/subscription"},
            {"checkout_url": "https://checkout.stripe.com/subscription"},
        ),
        (
            "get_artifact_access",
            {"has_access": True, "status": "unlocked", "expires_at": "2026-04-20T00:00:00Z"},
            {"has_access": True, "status": "unlocked", "expires_at": "2026-04-20T00:00:00Z"},
        ),
        (
            "consume_credit_unlock",
            {"consumed": True},
            {"consumed": True},
        ),
        (
            "get_account_dashboard",
            {"credits_remaining": 2, "dashboard_url": "https://billing.internal/account"},
            {"credits_remaining": 2, "dashboard_url": "https://billing.internal/account"},
        ),
    ],
)
def test_http_billing_client_parses_major_contract_methods(httpx_mock, method_name, payload, expected):
    client = HttpBillingClient(
        base_url="https://billing.internal",
        shared_token="secret-token",
        timeout_seconds=5.0,
    )

    routes = {
        "create_subscription_checkout": ("POST", "https://billing.internal/v1/checkout/subscription"),
        "get_artifact_access": ("GET", "https://billing.internal/v1/artifacts/artifact-1/access"),
        "consume_credit_unlock": ("POST", "https://billing.internal/v1/credits/consume"),
        "get_account_dashboard": ("GET", "https://billing.internal/v1/account/dashboard"),
    }
    method, url = routes[method_name]
    httpx_mock.add_response(method=method, url=url, json=payload)

    if method_name == "create_subscription_checkout":
        result = client.create_subscription_checkout(email="founder@example.com")
        assert result.checkout_url == expected["checkout_url"]
    elif method_name == "get_artifact_access":
        result = client.get_artifact_access(artifact_id="artifact-1", email="founder@example.com")
        assert result.has_access is expected["has_access"]
        assert result.status == expected["status"]
        assert result.expires_at == expected["expires_at"]
    elif method_name == "consume_credit_unlock":
        result = client.consume_credit_unlock(artifact_id="artifact-1", email="founder@example.com")
        assert result.consumed is expected["consumed"]
    else:
        result = client.get_account_dashboard(email="founder@example.com")
        assert result.credits_remaining == expected["credits_remaining"]
        assert result.dashboard_url == expected["dashboard_url"]


@pytest.mark.parametrize(
    ("method_name", "payload", "expected_message"),
    [
        ("create_guest_unlock_checkout", {"checkout_url": 123}, "guest unlock checkout: expected string field 'checkout_url'"),
        ("create_subscription_checkout", {"checkout_url": None}, "subscription checkout: expected string field 'checkout_url'"),
        (
            "get_artifact_access",
            {"has_access": "true", "status": "unlocked"},
            "artifact access: expected boolean field 'has_access'",
        ),
        (
            "get_artifact_access",
            {"has_access": True, "status": 1},
            "artifact access: expected string field 'status'",
        ),
        ("consume_credit_unlock", {"consumed": 1}, "credit unlock: expected boolean field 'consumed'"),
        (
            "get_account_dashboard",
            {"credits_remaining": "2", "dashboard_url": "https://billing.internal/account"},
            "account dashboard: expected integer field 'credits_remaining'",
        ),
        (
            "get_account_dashboard",
            {"credits_remaining": 2, "dashboard_url": 123},
            "account dashboard: expected string field 'dashboard_url'",
        ),
    ],
)
def test_http_billing_client_rejects_malformed_payloads(httpx_mock, method_name, payload, expected_message):
    client = HttpBillingClient(
        base_url="https://billing.internal",
        shared_token="secret-token",
        timeout_seconds=5.0,
    )

    routes = {
        "create_guest_unlock_checkout": ("POST", "https://billing.internal/v1/checkout/guest-unlock"),
        "create_subscription_checkout": ("POST", "https://billing.internal/v1/checkout/subscription"),
        "get_artifact_access": ("GET", "https://billing.internal/v1/artifacts/artifact-1/access"),
        "consume_credit_unlock": ("POST", "https://billing.internal/v1/credits/consume"),
        "get_account_dashboard": ("GET", "https://billing.internal/v1/account/dashboard"),
    }
    method, url = routes[method_name]
    httpx_mock.add_response(method=method, url=url, json=payload)

    with pytest.raises(BillingServiceError, match=expected_message):
        if method_name == "create_guest_unlock_checkout":
            client.create_guest_unlock_checkout(artifact_id="artifact-1", fingerprint="fp-1", email="founder@example.com")
        elif method_name == "create_subscription_checkout":
            client.create_subscription_checkout(email="founder@example.com")
        elif method_name == "get_artifact_access":
            client.get_artifact_access(artifact_id="artifact-1", email="founder@example.com")
        elif method_name == "consume_credit_unlock":
            client.consume_credit_unlock(artifact_id="artifact-1", email="founder@example.com")
        else:
            client.get_account_dashboard(email="founder@example.com")


@pytest.mark.parametrize(
    ("error", "status_code", "json_payload", "json_error"),
    [
        (requests.Timeout("slow"), 200, {"checkout_url": "x"}, None),
        (requests.ConnectionError("down"), 200, {"checkout_url": "x"}, None),
        (None, 500, {"checkout_url": "x"}, None),
        (None, 200, {"checkout_url": "x"}, ValueError("invalid json")),
        (None, 200, ["not", "an", "object"], None),
    ],
)
def test_http_billing_client_normalizes_transport_and_parsing_failures(httpx_mock, error, status_code, json_payload, json_error):
    client = HttpBillingClient(
        base_url="https://billing.internal",
        shared_token="secret-token",
        timeout_seconds=5.0,
    )

    httpx_mock.add_response(
        method="POST",
        url="https://billing.internal/v1/checkout/guest-unlock",
        json=json_payload,
        status_code=status_code,
        error=error,
        json_error=json_error,
    )

    with pytest.raises(BillingServiceError, match="billing service request failed|billing service response"):
        client.create_guest_unlock_checkout(
            artifact_id="artifact-1",
            fingerprint="fp-1",
            email="founder@example.com",
        )


def test_create_app_wires_billing_client_boundary():
    app = create_app(
        settings=Settings(
            billing_enabled=True,
            billing_service_base_url="https://billing.internal",
            billing_service_shared_token="secret-token",
        )
    )

    assert isinstance(app.state.billing_client, HttpBillingClient)


def test_create_app_uses_stub_billing_client_when_disabled():
    app = create_app(settings=Settings())

    assert isinstance(app.state.billing_client, StubBillingClient)
