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

    @staticmethod
    def _require_object(payload: object, *, context: str) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise BillingServiceError(f"{context}: expected JSON object")
        return payload

    @staticmethod
    def _require_str(payload: dict[str, object], key: str, *, context: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str):
            raise BillingServiceError(f"{context}: expected string field '{key}'")
        return value

    @staticmethod
    def _require_bool(payload: dict[str, object], key: str, *, context: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise BillingServiceError(f"{context}: expected boolean field '{key}'")
        return value

    @staticmethod
    def _require_int(payload: dict[str, object], key: str, *, context: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise BillingServiceError(f"{context}: expected integer field '{key}'")
        return value

    @staticmethod
    def _require_optional_str(payload: dict[str, object], key: str, *, context: str) -> str | None:
        if key not in payload or payload[key] is None:
            return None
        value = payload[key]
        if not isinstance(value, str):
            raise BillingServiceError(f"{context}: expected string field '{key}' or null")
        return value

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
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
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise BillingServiceError("billing service request failed") from exc

        return self._require_object(payload, context="billing service response")

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
        checkout_url = self._require_str(payload, "checkout_url", context="guest unlock checkout")
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
        checkout_url = self._require_str(payload, "checkout_url", context="subscription checkout")
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
            has_access=self._require_bool(payload, "has_access", context="artifact access"),
            status=self._require_str(payload, "status", context="artifact access"),
            expires_at=self._require_optional_str(payload, "expires_at", context="artifact access"),
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
        return CreditUnlockPayload(consumed=self._require_bool(payload, "consumed", context="credit unlock"))

    def get_account_dashboard(self, *, email: str) -> AccountDashboardPayload:
        payload = self._request("GET", "/v1/account/dashboard", params={"email": email})
        return AccountDashboardPayload(
            credits_remaining=self._require_int(payload, "credits_remaining", context="account dashboard"),
            dashboard_url=self._require_str(payload, "dashboard_url", context="account dashboard"),
        )


def build_billing_client(settings: Settings) -> BillingClient:
    if not settings.billing_enabled or not settings.billing_service_base_url or not settings.billing_service_shared_token:
        return StubBillingClient()
    return HttpBillingClient(
        base_url=settings.billing_service_base_url,
        shared_token=settings.billing_service_shared_token,
        timeout_seconds=settings.billing_timeout_seconds,
    )
