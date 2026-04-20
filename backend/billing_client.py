from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests

from .config import Settings


class BillingServiceError(RuntimeError):
    pass


@dataclass(slots=True)
class CheckoutSessionPayload:
    checkout_url: str


@dataclass(slots=True)
class ArtifactAccessPayload:
    has_access: bool
    status: str
    expires_at: str | None = None


@dataclass(slots=True)
class CreditUnlockPayload:
    consumed: bool


@dataclass(slots=True)
class AccountDashboardPayload:
    credits_remaining: int | None = None
    dashboard_url: str | None = None


class BillingClient(Protocol):
    def create_guest_unlock_checkout(
        self,
        *,
        artifact_id: str,
        fingerprint: str,
        email: str,
    ) -> CheckoutSessionPayload: ...

    def create_subscription_checkout(
        self,
        *,
        email: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> CheckoutSessionPayload: ...

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
    ) -> ArtifactAccessPayload: ...

    def consume_credit_unlock(
        self,
        *,
        artifact_id: str,
        email: str,
        fingerprint: str | None = None,
    ) -> CreditUnlockPayload: ...

    def get_account_dashboard(self, *, email: str) -> AccountDashboardPayload: ...


class StubBillingClient:
    def create_guest_unlock_checkout(
        self,
        *,
        artifact_id: str,
        fingerprint: str,
        email: str,
    ) -> CheckoutSessionPayload:
        raise BillingServiceError("billing service unavailable")

    def create_subscription_checkout(
        self,
        *,
        email: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> CheckoutSessionPayload:
        raise BillingServiceError("billing service unavailable")

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
    ) -> ArtifactAccessPayload:
        return ArtifactAccessPayload(has_access=False, status="billing_disabled")

    def consume_credit_unlock(
        self,
        *,
        artifact_id: str,
        email: str,
        fingerprint: str | None = None,
    ) -> CreditUnlockPayload:
        raise BillingServiceError("billing service unavailable")

    def get_account_dashboard(self, *, email: str) -> AccountDashboardPayload:
        raise BillingServiceError("billing service unavailable")


class HttpBillingClient:
    def __init__(
        self,
        *,
        base_url: str,
        shared_token: str,
        timeout_seconds: float,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.shared_token = shared_token
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    @staticmethod
    def _compact_values(values: dict[str, object | None]) -> dict[str, object]:
        return {key: value for key, value in values.items() if value is not None}

    def _request(self, method: str, path: str, *, json: dict[str, object] | None = None, params: dict[str, object] | None = None) -> dict:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.shared_token}"},
            json=json,
            params=self._compact_values(params or {}),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise BillingServiceError("billing service returned a non-object response")
        return payload

    def create_guest_unlock_checkout(
        self,
        *,
        artifact_id: str,
        fingerprint: str,
        email: str,
    ) -> CheckoutSessionPayload:
        payload = self._request(
            "POST",
            "/v1/checkout/guest-unlock",
            json={
                "artifact_id": artifact_id,
                "fingerprint": fingerprint,
                "email": email,
            },
        )
        checkout_url = payload.get("checkout_url")
        if not isinstance(checkout_url, str):
            raise BillingServiceError("billing service response missing checkout_url")
        return CheckoutSessionPayload(checkout_url=checkout_url)

    def create_subscription_checkout(
        self,
        *,
        email: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> CheckoutSessionPayload:
        payload = self._request(
            "POST",
            "/v1/checkout/subscription",
            json={
                "email": email,
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
        )
        checkout_url = payload.get("checkout_url")
        if not isinstance(checkout_url, str):
            raise BillingServiceError("billing service response missing checkout_url")
        return CheckoutSessionPayload(checkout_url=checkout_url)

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
    ) -> ArtifactAccessPayload:
        payload = self._request(
            "GET",
            f"/v1/artifacts/{artifact_id}/access",
            params={
                "email": email,
                "fingerprint": fingerprint,
            },
        )
        return ArtifactAccessPayload(
            has_access=bool(payload.get("has_access", False)),
            status=str(payload.get("status", "unknown")),
            expires_at=payload.get("expires_at") if isinstance(payload.get("expires_at"), str) else None,
        )

    def consume_credit_unlock(
        self,
        *,
        artifact_id: str,
        email: str,
        fingerprint: str | None = None,
    ) -> CreditUnlockPayload:
        payload = self._request(
            "POST",
            "/v1/credits/consume",
            json={
                "artifact_id": artifact_id,
                "email": email,
                "fingerprint": fingerprint,
            },
        )
        return CreditUnlockPayload(consumed=bool(payload.get("consumed", False)))

    def get_account_dashboard(self, *, email: str) -> AccountDashboardPayload:
        payload = self._request("GET", "/v1/account/dashboard", params={"email": email})
        credits_remaining = payload.get("credits_remaining")
        return AccountDashboardPayload(
            credits_remaining=credits_remaining if isinstance(credits_remaining, int) else None,
            dashboard_url=payload.get("dashboard_url") if isinstance(payload.get("dashboard_url"), str) else None,
        )


def build_billing_client(settings: Settings) -> BillingClient:
    if not settings.billing_enabled or not settings.billing_service_base_url or not settings.billing_service_shared_token:
        return StubBillingClient()
    return HttpBillingClient(
        base_url=settings.billing_service_base_url,
        shared_token=settings.billing_service_shared_token,
        timeout_seconds=settings.billing_timeout_seconds,
    )
