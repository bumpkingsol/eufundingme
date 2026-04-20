from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests

from .config import Settings


class BillingServiceError(RuntimeError):
    pass


class BillingServiceUnavailableError(BillingServiceError):
    pass


class BillingUnauthorizedError(BillingServiceError):
    pass


class BillingForbiddenError(BillingServiceError):
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


class AccountContextLike(Protocol):
    session_token: str | None
    email_hint: str | None
    fingerprint_hint: str | None


class BillingClient(Protocol):
    def create_guest_unlock_checkout(
        self,
        *,
        artifact_id: str,
        fingerprint: str,
        email: str | None,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload: ...

    def create_subscription_checkout(
        self,
        *,
        email: str | None,
        success_url: str | None = None,
        cancel_url: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload: ...

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> ArtifactAccessPayload: ...

    def consume_credit_unlock(
        self,
        *,
        artifact_id: str,
        email: str | None,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CreditUnlockPayload: ...

    def get_account_dashboard(
        self,
        *,
        email: str | None,
        account_context: AccountContextLike | None = None,
    ) -> AccountDashboardPayload: ...


class StubBillingClient:
    def create_guest_unlock_checkout(
        self,
        *,
        artifact_id: str,
        fingerprint: str,
        email: str,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload:
        raise BillingServiceUnavailableError("billing service unavailable")

    def create_subscription_checkout(
        self,
        *,
        email: str,
        success_url: str | None = None,
        cancel_url: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload:
        raise BillingServiceUnavailableError("billing service unavailable")

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> ArtifactAccessPayload:
        return ArtifactAccessPayload(has_access=False, status="billing_disabled")

    def consume_credit_unlock(
        self,
        *,
        artifact_id: str,
        email: str,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CreditUnlockPayload:
        raise BillingServiceUnavailableError("billing service unavailable")

    def get_account_dashboard(
        self,
        *,
        email: str,
        account_context: AccountContextLike | None = None,
    ) -> AccountDashboardPayload:
        raise BillingServiceUnavailableError("billing service unavailable")


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
    def _build_headers(account_context: AccountContextLike | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if account_context is None:
            return headers
        session_token = getattr(account_context, "session_token", None)
        if session_token:
            headers["X-Account-Session"] = session_token
            return headers
        if getattr(account_context, "email_hint", None):
            headers["X-Account-Email"] = account_context.email_hint or ""
        if getattr(account_context, "fingerprint_hint", None):
            headers["X-Artifact-Fingerprint"] = account_context.fingerprint_hint or ""
        return headers

    @staticmethod
    def _sanitize_identity(
        *,
        account_context: AccountContextLike | None,
        email: str | None = None,
        fingerprint: str | None = None,
    ) -> tuple[str | None, str | None]:
        if account_context is not None and getattr(account_context, "session_token", None):
            return None, None
        return email, fingerprint

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
        account_context: AccountContextLike | None = None,
    ) -> dict[str, object]:
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.shared_token}",
                    **self._build_headers(account_context),
                },
                json=json,
                params=self._compact_values(params or {}),
                timeout=self.timeout_seconds,
            )
            if response.status_code == 401:
                raise BillingUnauthorizedError("billing service unauthorized")
            if response.status_code == 403:
                raise BillingForbiddenError("billing service forbidden")
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
        email: str | None,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload:
        email, fingerprint = self._sanitize_identity(
            account_context=account_context,
            email=email,
            fingerprint=fingerprint,
        )
        json_payload: dict[str, object | None] = {"artifact_id": artifact_id}
        if email is not None:
            json_payload["email"] = email
        if fingerprint is not None:
            json_payload["fingerprint"] = fingerprint
        payload = self._request(
            "POST",
            "/v1/checkout/guest-unlock",
            json=json_payload,
            account_context=account_context,
        )
        checkout_url = self._require_str(payload, "checkout_url", context="guest unlock checkout")
        return CheckoutSessionPayload(checkout_url=checkout_url)

    def create_subscription_checkout(
        self,
        *,
        email: str | None,
        success_url: str | None = None,
        cancel_url: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CheckoutSessionPayload:
        email, _ = self._sanitize_identity(account_context=account_context, email=email)
        json_payload: dict[str, object | None] = {
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        if email is not None:
            json_payload["email"] = email
        payload = self._request(
            "POST",
            "/v1/checkout/subscription",
            json=json_payload,
            account_context=account_context,
        )
        checkout_url = self._require_str(payload, "checkout_url", context="subscription checkout")
        return CheckoutSessionPayload(checkout_url=checkout_url)

    def get_artifact_access(
        self,
        *,
        artifact_id: str,
        email: str | None = None,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> ArtifactAccessPayload:
        email, fingerprint = self._sanitize_identity(
            account_context=account_context,
            email=email,
            fingerprint=fingerprint,
        )
        payload = self._request(
            "GET",
            f"/v1/artifacts/{artifact_id}/access",
            params={
                "email": email,
                "fingerprint": fingerprint,
            },
            account_context=account_context,
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
        email: str | None,
        fingerprint: str | None = None,
        account_context: AccountContextLike | None = None,
    ) -> CreditUnlockPayload:
        email, fingerprint = self._sanitize_identity(
            account_context=account_context,
            email=email,
            fingerprint=fingerprint,
        )
        json_payload: dict[str, object | None] = {"artifact_id": artifact_id}
        if email is not None:
            json_payload["email"] = email
        if fingerprint is not None:
            json_payload["fingerprint"] = fingerprint
        payload = self._request(
            "POST",
            "/v1/credits/consume",
            json=json_payload,
            account_context=account_context,
        )
        return CreditUnlockPayload(consumed=self._require_bool(payload, "consumed", context="credit unlock"))

    def get_account_dashboard(
        self,
        *,
        email: str | None,
        account_context: AccountContextLike | None = None,
    ) -> AccountDashboardPayload:
        email, _ = self._sanitize_identity(account_context=account_context, email=email)
        params: dict[str, object | None] = {}
        if email is not None:
            params["email"] = email
        payload = self._request(
            "GET",
            "/v1/account/dashboard",
            params=params,
            account_context=account_context,
        )
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
