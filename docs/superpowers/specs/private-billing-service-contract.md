# Private Billing Service Contract

## Purpose

This document defines the exact boundary between the public EU Grant Matcher app and the private billing service that lives in a separate closed repository.

The public app is preview-first and keeps search-artifact generation, preview rendering, and locked-result UX in the open-source repo. The private billing service owns Stripe checkout, entitlement decisions, credit consumption, and subscriber dashboard state.

## Transport

All requests from the public app to the private billing service use HTTPS and JSON.

Every request includes:

- `Authorization: Bearer <BILLING_SERVICE_SHARED_TOKEN>`
- `X-Account-Session: <opaque session token>` when the public app has a resolved session context
- `X-Account-Email: <hint>` only when no opaque session token is present and an email hint exists
- `X-Artifact-Fingerprint: <hint>` only when no opaque session token is present and a fingerprint hint exists

Identity rules:

- The opaque session token takes priority over raw email and fingerprint hints.
- If `X-Account-Session` is present, the private service must treat email and fingerprint as advisory hints only and ignore them for authorization.
- If the private service cannot authenticate the shared service token, it must return `401` with a normalized error payload using `UNAUTHENTICATED`.

## Error Envelope

For non-2xx responses, the private service should return a JSON object of the form:

```json
{
  "code": "UNAUTHENTICATED",
  "message": "human readable summary",
  "request_id": "optional-trace-id",
  "details": {}
}
```

Fields:

- `code` is required and machine-readable.
- `message` is required and human-readable.
- `request_id` is optional and should be echoed back when the request included one.
- `details` is optional and may carry operation-specific debugging context.

The public app converts private-service auth and access failures into its own HTTP responses, but the private service should use the normalized codes below for its own boundary.

## Endpoints

### 1) Guest unlock checkout creation

Public app route:

- `POST /api/billing/guest-checkout`

Private service endpoint:

- `POST /v1/checkout/guest-unlock`

Request body:

```json
{
  "artifact_id": "artifact-1",
  "email": "founder@example.com",
  "fingerprint": "fp-1"
}
```

Request field rules:

- `artifact_id` is required and identifies the cached search artifact being purchased.
- `email` is required when the public app only has a raw email hint.
- `fingerprint` is required when the public app only has a raw fingerprint hint.
- Either field may be omitted when the opaque session context already identifies the user.

Successful response:

```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_123"
}
```

Failure contracts:

- `UNAUTHENTICATED` if the service token or session context is invalid. The public app preserves this boundary as `BILLING_UNAUTHORIZED` or `BILLING_FORBIDDEN` when the private service returns a 401 or 403.
- `BILLING_UNAVAILABLE` if Stripe or downstream billing dependencies are unavailable. The public app also flattens non-auth failures from this route into `BILLING_UNAVAILABLE` today.
- `ARTIFACT_LOCKED` may be used internally by the private service to describe an ineligible artifact, but the current public app does not preserve that code across this checkout boundary.

### 2) Subscription checkout creation

Public app route:

- `POST /api/billing/subscription-checkout`

Private service endpoint:

- `POST /v1/checkout/subscription`

Request body:

```json
{
  "email": "founder@example.com",
  "success_url": "https://fundingme.eu/account?checkout=success",
  "cancel_url": "https://fundingme.eu/account?checkout=cancel"
}
```

Request field rules:

- `email` is the billing identity hint for the account session.
- `success_url` and `cancel_url` are always present in the request body and may be `null`.
- If an opaque session token is present, the private service must prefer that token over the raw email hint.

Successful response:

```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_456"
}
```

Failure contracts:

- `UNAUTHENTICATED` if the service token or session context is invalid.
- `BILLING_UNAVAILABLE` if Stripe or downstream billing dependencies are unavailable.

### 3) Artifact access check

Public app route:

- `GET /api/search-artifacts/{artifact_id}/access`

Private service endpoint:

- `GET /v1/artifacts/{artifact_id}/access`

Query parameters:

```text
email=founder@example.com
fingerprint=fp-1
```

Request field rules:

- `artifact_id` is the immutable search-artifact identifier.
- `email` and `fingerprint` are optional hints and may be omitted.
- If an opaque session token is present, the private service must authorize from that session first.

Successful response:

```json
{
  "has_access": false,
  "status": "pending_unlock",
  "expires_at": "2026-04-20T00:00:00Z"
}
```

`status` is the access decision used by the public app. Supported values are:

- `preview`
- `pending_unlock`
- `pending_payment`
- `requires_payment`
- `unlocked`
- `expired`

Failure contracts:

- `UNAUTHENTICATED` if the service token or session context is invalid. The public app preserves this boundary as `BILLING_UNAUTHORIZED` or `BILLING_FORBIDDEN` when the private service returns a 401 or 403.
- `BILLING_UNAVAILABLE` if the billing system cannot evaluate access.
- `ARTIFACT_LOCKED` is generated by the public app after a successful access response when `has_access=false` and a protected route needs to block access. The access-check endpoint itself does not preserve an upstream `ARTIFACT_LOCKED` code today.

Implementation note:

- The public app treats a `200` response with `status="expired"` as a normal expired-access decision.
- The public app does not currently preserve `ARTIFACT_EXPIRED` as an upstream normalized failure from this boundary.

### 4) Credit unlock consumption

Public app route:

- `POST /api/search-artifacts/{artifact_id}/unlock-with-credit`

Private service endpoint:

- `POST /v1/credits/consume`

Request body:

```json
{
  "artifact_id": "artifact-1",
  "email": "founder@example.com",
  "fingerprint": "fp-1"
}
```

Request field rules:

- `artifact_id` identifies the search artifact whose credit cost is being paid.
- `email` is required when no opaque session token is available.
- `fingerprint` is optional and helps restore guest purchases across devices.

Successful response:

```json
{
  "consumed": true
}
```

Failure contracts:

- `UNAUTHENTICATED` if the service token or session context is invalid. The public app preserves this boundary as `BILLING_UNAUTHORIZED` or `BILLING_FORBIDDEN` when the private service returns a 401 or 403.
- `BILLING_UNAVAILABLE` if Stripe or downstream billing dependencies are unavailable. The public app also flattens non-auth failures from this route into `BILLING_UNAVAILABLE` today.
- `ARTIFACT_LOCKED` may be used internally by the private service to reject a credit unlock, but the current public app does not preserve that code across this boundary.
- `INSUFFICIENT_CREDITS` may be used internally by the private service to describe ledger exhaustion, but the current public app does not preserve that code across this boundary.

Consumption semantics:

- Credit consumption must be idempotent for the same artifact and entitlement state.
- A successful consumption should be followed by a successful access check for the same artifact and identity.

### 5) Dashboard fetch

Public app route:

- `GET /api/account/dashboard`

Private service endpoint:

- `GET /v1/account/dashboard`

Query parameters:

```text
email=founder@example.com
```

Request field rules:

- `email` is the billing account hint when no opaque session token is available.
- If an opaque session token is present, the private service must use it first and may ignore the raw email hint for authorization.

Successful response:

```json
{
  "credits_remaining": 7,
  "dashboard_url": "https://billing.example/account"
}
```

Failure contracts:

- `UNAUTHENTICATED` if the service token or session context is invalid.
- `BILLING_UNAVAILABLE` if the dashboard state cannot be fetched.

## Normalized Failure Codes

The private billing service may normalize these codes internally:

- `BILLING_UNAVAILABLE`
  - The private service cannot reach Stripe, cannot reach its database, or is otherwise unable to fulfill the request.
  - The public app treats this as `BILLING_UNAVAILABLE` when the failure is not a 401 or 403.
- `ARTIFACT_LOCKED`
  - The artifact exists, but the current identity does not have an active entitlement for it.
  - The public app does not currently preserve this code across the guest checkout, access check, or credit unlock HTTP boundary.
- `ARTIFACT_EXPIRED`
  - The entitlement existed, but the unlock window has lapsed.
- `INSUFFICIENT_CREDITS`
  - The account is authenticated, but the credit ledger cannot cover the unlock request.
  - The public app does not currently preserve this code across the guest checkout or credit unlock HTTP boundary.
- `UNAUTHENTICATED`
  - The shared service token is missing or invalid, or the opaque session token cannot be verified.
  - The public app preserves this code as `BILLING_UNAUTHORIZED` or `BILLING_FORBIDDEN` when the private service returns a 401 or 403.

Current public-app boundary behavior:

- `401` and `403` are preserved as `BILLING_UNAUTHORIZED` / `BILLING_FORBIDDEN`
- all other private billing failures on these routes are flattened to `BILLING_UNAVAILABLE`
- `ARTIFACT_LOCKED` remains a public-app-local result produced after a successful access response with `has_access=false`
- `INSUFFICIENT_CREDITS` remains a private-service internal code and is not surfaced separately by the current public app boundary

The exact status code may vary if the private service has a stronger domain-specific reason, but the `code` field must remain stable.

## Contract Summary

The open-source public app expects:

- checkout creation to return only a Stripe Checkout URL
- access checks to return a compact entitlement decision
- credit unlocks to return a consumed flag
- dashboard reads to return the current credit balance and dashboard URL

Anything beyond that stays private in the closed billing repo.
