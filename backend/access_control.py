from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from .billing_client import BillingServiceError


@dataclass(slots=True)
class AccountContext:
    email: str | None = None
    fingerprint: str | None = None


def resolve_account_context(request: Request) -> AccountContext:
    email = request.headers.get("X-Account-Email") or request.headers.get("X-Email")
    fingerprint = request.headers.get("X-Artifact-Fingerprint") or request.headers.get("X-Fingerprint")
    return AccountContext(
        email=email.strip() if isinstance(email, str) and email.strip() else None,
        fingerprint=fingerprint.strip() if isinstance(fingerprint, str) and fingerprint.strip() else None,
    )


def require_artifact_access(*, billing_client, artifact_id: str, account_context: AccountContext):
    try:
        decision = billing_client.get_artifact_access(
            artifact_id=artifact_id,
            email=account_context.email,
            fingerprint=account_context.fingerprint,
        )
    except BillingServiceError as exc:
        raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc

    if not getattr(decision, "has_access", False):
        raise HTTPException(status_code=403, detail={"code": "ARTIFACT_LOCKED"})
    return decision
