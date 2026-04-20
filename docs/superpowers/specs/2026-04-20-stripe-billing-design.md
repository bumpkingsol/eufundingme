# Stripe Billing Design

## Goal

Add a monetization layer to the hosted EU Grant Matcher so users can run a free preview search, see the top result immediately, and then pay to unlock the full result set and application brief. The monetization model should support both one-off buyers and repeat users, while keeping the real payment infrastructure and entitlement logic outside the open-source repository.

## Scope

### In scope

- Add a free preview flow that shows the top 1 result and locks the rest.
- Compute and cache the full ranked search artifact before payment so unlocks feel instant.
- Support guest one-off unlock purchases for a single company or project search.
- Support account-based subscriptions with monthly credits and top-up purchases.
- Use one credit to unlock one search artifact for 7 days, including all results and the application brief.
- Add teaser cards for locked results so the paywall sells concrete hidden value.
- Add account access based on magic-link sign-in for subscription users.
- Keep Stripe secrets, webhooks, pricing logic, entitlement logic, and customer state in a separate private billing service.
- Define the public app to private billing service contract at a high level.

### Out of scope

- Team workspaces, shared company libraries, or admin roles.
- Enterprise invoicing workflows beyond self-serve business checkout.
- Deep procurement features.
- Final pricing numbers.
- Implementation of the private billing service in this repository.
- Full self-hosted paid commerce support in the open-source version.

## Product Model

### Free preview

- A visitor runs a search with the existing company description flow.
- The backend computes the full ranked result set once and stores it as a search artifact.
- The UI shows the top 1 result fully.
- The remaining results are presented as locked teaser cards.
- The application brief remains locked.
- The page clearly communicates that more matches are ready to unlock.

### One-off unlock

- A guest user can pay once to unlock the full search artifact for 7 days.
- The unlock includes:
  - all hidden result cards
  - full match explanations
  - application brief generation for that unlocked artifact
- The unlock is tied to `email + search fingerprint`.
- The unlock should restore across devices once the user proves control of the same email address.

### Subscription

- Subscription users sign in with magic links.
- A subscription grants monthly credits rather than unlimited usage.
- Credits can be topped up separately.
- One credit unlocks one search artifact for 7 days.
- A subscriber dashboard shows:
  - current credit balance
  - unlocked searches
  - billing and renewal state
  - top-up actions

## Why This Model

### Recommended commercial strategy

Use a hybrid model:

- free preview for acquisition
- one-off unlock for low-friction conversion
- subscription with monthly credits for repeat usage

This should outperform subscription-only or per-result monetization because it:

- keeps the first paid action simple
- preserves user momentum after the first visible match
- creates a clean ladder from casual use to recurring revenue
- avoids per-result friction that usually depresses conversion and trust

### Unlock unit

The paid unit should be a full search unlock, not a per-result unlock.

One paid unlock or one consumed credit should grant:

- full result access for that artifact
- application brief access
- 7 days of access for that company or project search

This sells an outcome rather than monetizing individual rows or actions.

## User Experience

### Free visitor flow

- User lands on the existing site and submits a company description.
- The backend computes and stores the full search artifact.
- The UI renders:
  - one fully visible result
  - a strong locked-results message such as `11 more matches ready to unlock`
  - teaser cards for remaining matches
  - CTA for a one-off unlock
  - CTA for subscription if the user is likely to run more searches

### Locked result teaser design

Each teaser card should expose enough information to create desire without giving away the core value:

- title
- fit score band or confidence band
- optional deadline or budget teaser metadata
- locked explanation state
- unlock CTA

The following stay locked:

- full `why_match`
- full `application_angle`
- full result set access
- application brief generation

### Guest one-off flow

- User clicks unlock from the preview experience.
- Stripe Checkout collects payment and email.
- The private billing service fulfills the purchase through webhook processing.
- The app then unlocks the artifact instantly without recomputation.
- The user receives a receipt or access email with a prompt to claim future access through magic link if needed.

### Subscriber flow

- User signs in with a magic link.
- User subscribes to a plan that grants monthly credits.
- Stripe webhook grants the subscription state and credit balance in the private billing service.
- When the subscriber unlocks an artifact, one credit is consumed.
- Access lasts 7 days for that artifact.
- Dashboard provides account visibility and upgrade paths.

## Architecture

### High-level split

The architecture should be explicitly split between:

- open-source public application repo
- private billing and entitlement service

The public app remains responsible for:

- search input and matching UX
- search artifact generation
- preview rendering
- locked state rendering
- account-facing UI shells for checkout and dashboard

The private billing service remains responsible for:

- Stripe Checkout session creation
- Stripe customer and subscription management
- webhook verification and fulfillment
- pricing catalog rules
- credit ledger state
- entitlement decisions
- guest purchase restoration rules
- magic-link account issuance and access verification, if centralized there

### Search artifact model

The app backend should compute the full result set before payment and persist a `search artifact`.

That artifact should include:

- normalized search input
- search fingerprint
- preview-ready result payload
- full ranked results payload
- application brief seed context
- timestamps and expiry metadata
- request trace metadata

Unlocking should never rerun the search when the artifact is still valid. Payment changes access rights, not search computation.

### Billing integration pattern

The public app should integrate with the private service through a narrow adapter boundary, for example:

- `BillingClient.create_checkout_session(...)`
- `BillingClient.get_access_decision(...)`
- `BillingClient.consume_credit_for_artifact(...)`
- `BillingClient.get_account_dashboard(...)`

The open-source repo should contain only the interface or client contract and a development stub. Production billing logic should live outside this repository.

## Data Model

### Public app records

#### `search_artifact`

- `id`
- `fingerprint`
- `normalized_company_input`
- `preview_result_payload`
- `full_result_payload`
- `application_brief_seed_data`
- `result_count`
- `created_at`
- `expires_at`
- `source_request_id`
- `pricing_version`
- `status`

The artifact stores the expensive work product of the match operation and supports instant unlocks.

### Private billing records

#### `guest_unlock`

- `id`
- `email`
- `search_artifact_id`
- `fingerprint`
- `stripe_checkout_session_id`
- `stripe_payment_intent_id`
- `unlocked_at`
- `expires_at`

#### `account`

- `id`
- `email`
- `stripe_customer_id`
- `created_at`
- `last_login_at`

#### `subscription`

- `account_id`
- `stripe_subscription_id`
- `status`
- `current_period_start`
- `current_period_end`
- `plan_key`

#### `credit_ledger`

- `id`
- `account_id`
- `delta`
- `reason`
- `related_search_artifact_id`
- `stripe_invoice_id` or `stripe_checkout_session_id`
- `created_at`

#### `artifact_access_grant`

- `id`
- `account_id`
- `search_artifact_id`
- `granted_via`
- `granted_at`
- `expires_at`

## Access Rules

- Anyone can receive a preview artifact response.
- Full result access requires a valid unlock or access grant.
- A guest unlock is tied to `email + search fingerprint`.
- A subscriber unlock consumes one credit only once per artifact.
- Access lasts 7 days from unlock time.
- The frontend never grants access based only on client checkout success.
- Webhook fulfillment and server-to-server entitlement checks are the source of truth.

## Public App API Shape

### Match preview response changes

The current match response should evolve to support preview mode. At a high level the frontend needs:

- the visible top result
- teaser metadata for locked results
- total locked result count
- search artifact identifier
- artifact expiry metadata
- billing presentation metadata
- access state such as `preview`, `pending_unlock`, `unlocked`, or `expired`

The public app should not receive or persist Stripe secrets or private billing internals.

### App to private billing service interactions

Representative operations:

- create a one-off checkout session for a guest unlock
- create a subscription checkout session
- poll for unlock state after payment
- ask whether the current session or email has access to artifact `X`
- consume a credit for a subscriber unlock
- fetch account dashboard data

These should be narrow, explicit server-to-server calls with stable contracts.

## Open-source Boundary

### Must remain private

The following must not live in the open-source repository:

- Stripe secret keys
- webhook handling and signature verification
- price catalog source of truth
- subscription state management
- credit ledger business logic
- entitlement granting logic
- guest purchase restoration logic beyond public request stubs
- production magic-link authentication implementation if it exposes the commercial access model

### Open-source-safe behavior

The public repository can safely include:

- billing client interfaces
- stubbed billing adapters for local development
- preview-only fallback behavior when no billing service is configured
- frontend paywall UI states
- public search artifact generation

In self-hosted mode, the app should degrade gracefully, for example by operating in preview-only mode unless an operator supplies their own billing adapter.

## Error Handling

- If search artifact creation succeeds but the billing service is unavailable, still show the free preview and render unlock actions as temporarily unavailable.
- If checkout succeeds in the browser but webhook fulfillment is still pending, show a pending-unlock state and poll the server for completion.
- If an artifact expires before fulfillment completes, reject the unlock and ask the user to rerun the search.
- If credit consumption fails, do not grant access optimistically.
- If the private billing service is down, paid access should fail closed while preview search remains available.

## Security

- Stripe secrets stay in the private service only.
- Webhook verification happens in the private service only.
- Access checks happen server-to-server, never through client-trusted flags.
- Guest purchase restoration on a fresh device should require email verification before exposing paid content.
- Credit ledger updates should be append-only for auditability.
- Artifact identifiers exposed to clients should be narrow and opaque enough to avoid coupling external callers to internal storage details.

## Testing

### Public app tests

- Preview responses include one visible result plus locked teaser metadata.
- Locked results cannot be fetched without entitlement.
- Expired artifacts behave correctly.
- Unlock UI degrades safely when the billing service is unavailable.
- Subscriber unlock flow consumes one credit only once per artifact at the contract boundary.

### Private billing service tests

- Checkout session creation for guest unlocks and subscriptions.
- Webhook verification and idempotent fulfillment.
- Guest unlock grant creation.
- Monthly credit grants.
- Top-up credit grants.
- Credit consumption.
- Artifact access decisions.
- Guest purchase claim and account attachment by email.

### Integration tests

- Free preview to payment to unlock without recomputation.
- Guest unlock restoration on another device after email verification.
- Subscriber unlock consumes one credit and re-opening the same artifact during the 7-day window does not consume another credit.
- Duplicate webhook deliveries do not double-grant credits or access.

## Recommendation

Implement monetization as a hybrid preview plus unlock system where the public app owns search artifact generation and a private billing service owns Stripe, credits, subscriptions, and access rights. This preserves the open-source value of the application while keeping the revenue engine proprietary, and it creates the strongest balance of acquisition, conversion, and recurring revenue for the hosted service.
