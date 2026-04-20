from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request

from .billing_client import BillingServiceError


@dataclass(slots=True)
class AccountContext:
    session_token: str | None = None
    email_hint: str | None = None
    fingerprint_hint: str | None = None

    def has_identity(self) -> bool:
        return any((self.session_token, self.email_hint, self.fingerprint_hint))


def resolve_account_context(request: Request) -> AccountContext:
    authorization = request.headers.get("Authorization", "")
    session_token = request.headers.get("X-Account-Session") or request.headers.get("X-Session-Token")
    if authorization.startswith("Bearer "):
        session_token = session_token or authorization.removeprefix("Bearer ").strip()
    email_hint = request.headers.get("X-Account-Email") or request.headers.get("X-Email")
    fingerprint_hint = request.headers.get("X-Artifact-Fingerprint") or request.headers.get("X-Fingerprint")
    return AccountContext(
        session_token=session_token.strip() if isinstance(session_token, str) and session_token.strip() else None,
        email_hint=email_hint.strip() if isinstance(email_hint, str) and email_hint.strip() else None,
        fingerprint_hint=fingerprint_hint.strip() if isinstance(fingerprint_hint, str) and fingerprint_hint.strip() else None,
    )


def require_artifact_access(
    *,
    billing_client,
    artifact_id: str,
    account_context: AccountContext,
    on_billing_error: Callable[[BillingServiceError], None] | None = None,
):
    try:
        decision = billing_client.get_artifact_access(
            artifact_id=artifact_id,
            account_context=account_context,
            email=account_context.email_hint,
            fingerprint=account_context.fingerprint_hint,
        )
    except BillingServiceError as exc:
        if on_billing_error is not None:
            on_billing_error(exc)
        raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc

    if not getattr(decision, "has_access", False):
        raise HTTPException(status_code=403, detail={"code": "ARTIFACT_LOCKED"})
    return decision
