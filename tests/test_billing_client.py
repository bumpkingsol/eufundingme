from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from backend.app import create_app
from backend.billing_client import HttpBillingClient, StubBillingClient
from backend.config import Settings


@dataclass(slots=True)
class _QueuedResponse:
    method: str
    url: str
    json_payload: dict[str, object]
    status_code: int = 200


class _MockHttpx:
    def __init__(self) -> None:
        self.responses: list[_QueuedResponse] = []
        self.calls: list[dict[str, object]] = []

    def add_response(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, object],
        status_code: int = 200,
    ) -> None:
        self.responses.append(_QueuedResponse(method=method, url=url, json_payload=json, status_code=status_code))


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

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict[str, object]) -> None:
                self.status_code = status_code
                self._payload = payload

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise requests.HTTPError(f"status {self.status_code}")

            def json(self) -> dict[str, object]:
                return self._payload

        return FakeResponse(expected.status_code, expected.json_payload)

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
