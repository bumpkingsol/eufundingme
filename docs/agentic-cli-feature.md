# Agentic CLI Request Correlation & Installable Entrypoint

## Overview

This feature makes CLI matching safe for autonomous agents by enforcing deterministic machine contracts and stable request tracing, while preserving existing local invocation paths.

- CLI/API match operations now share a trace identifier (`request_id`) contract.
- Match readiness is enforced with explicit waiting/timeout behavior for automation reliability.
- A first-class package install entrypoint (`eufundingme`) is added without removing compatibility shims.

## Why

Autonomous agents require:

- Deterministic JSON output for control flow.
- Predictable exit codes for branching and retries.
- Correlation IDs to trace requests across tool runs and logs.
- A portable command surface that works when run outside the repository clone.

## Implemented Behavior

### 0) UI handoff for external agents

- The web UI now exposes an `Agent Handoff` block in the hero area.
- It includes a `Copy Instructions` action that copies a ready-to-paste bootstrap brief for external agents.
- The copied instructions tell the agent how to install, verify, and use the CLI tool autonomously, with `eufundingme` as the preferred path and `python -m backend.cli ...` as the fallback.

### 1) Request ID generation and propagation

Shared utility:

- `backend/request_ids.py`
  - `resolve_request_id(request_id: str | None) -> str`
  - Generates `uuid.uuid4().hex` when no ID is supplied.

### 2) CLI behavior

Match command now supports:

- `--request-id <value>`: explicit correlation override.
- Default generation when `--request-id` is omitted.
- Generated/overridden ID is included in:
  - successful match envelope
  - `INDEX_NOT_READY` error envelope
  - `MATCH_TIMEOUT` error envelope
  - `INTERNAL_ERROR` envelope

Other commands remain unchanged and keep the existing JSON-first behavior.

#### CLI command contract

- Entry command: `match`
- Matching arguments:
  - `--description` (required)
  - `--wait-timeout-seconds` (optional override for readiness wait)
  - `--poll-interval-seconds` (default `0.5`)
  - `--request-id` (new optional override)
- Default machine output is JSON.
- Optional `--text` output remains available.
- Exit codes:
  - `0` success
  - `2` validation / readiness blocked (`INDEX_NOT_READY`)
  - `3` readiness timeout (`MATCH_TIMEOUT`)
  - `1` runtime failure (`INTERNAL_ERROR`)

Error payload shape:

```json
{
  "ok": false,
  "error": {
    "code": "INDEX_NOT_READY",
    "message": "Index is not ready for matching.",
    "status": { "...": "..." }
  },
  "request_id": "..."
}
```

Success payload shape (truncated):

```json
{
  "ok": true,
  "request_id": "...",
  "indexed_grants": 42,
  "results": [...],
  "status": {...}
}
```

### 3) API behavior

- `POST /api/match` now reads request header:
  - `X-Request-ID` (explicit override)
- If missing, API uses generated `uuid.uuid4().hex`.
- Successful match responses now include top-level `request_id`.
- Unreadiness (503) detail payload now includes `request_id`.
- Existing not-ready semantics remain unchanged (`INDEX_NOT_READY`).

Success response example (truncated):

```json
{
  "request_id": "...",
  "indexed_grants": 42,
  "results": [...]
}
```

Response example when unavailable:

```json
{
  "detail": {
    "code": "INDEX_NOT_READY",
    "message": "Index is not ready for matching.",
    "status": {...},
    "request_id": "..."
  }
}
```

### 4) Installability

- Added `pyproject.toml` with package metadata and console script:
  - `eufundingme = "backend.cli:main"`
- Backward compatibility preserved:
  - `python -m backend.cli ...`
  - `scripts/eufundingme ...` as a repo-local shim that expects the checkout `.venv` or an environment with backend dependencies installed
- This enables agent execution from isolated environments after install:
  - `pip install -e .` (or `pip install .`)

## Files Changed

- [backend/request_ids.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/backend/request_ids.py)
- [backend/cli_services.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/backend/cli_services.py)
- [backend/cli.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/backend/cli.py)
- [backend/app.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/backend/app.py)
- [pyproject.toml](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/pyproject.toml)
- [README.md](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/README.md)

## Test Coverage

- CLI parser + command behavior:
  - [tests/cli/test_parser.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/tests/cli/test_parser.py)
  - [tests/cli/test_match_command.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/tests/cli/test_match_command.py)
- API contract tests:
  - [tests/test_api.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/tests/test_api.py)
- CLI/install smoke tests:
  - [tests/cli/test_cli_smoke.py](/Users/jonassorensen/Desktop/Hobby/eufundingme/eufundingme/tests/cli/test_cli_smoke.py)

## Verification

- Run:
  - `python -m pytest -q`
- Validate installed entrypoint:
  - `pip install -e .`
  - `eufundingme --help`
  - `eufundingme match --description "..." --json`

## Rollout Notes

- New behavior is additive and backwards-compatible:
  - existing non-request-id callers keep working
  - shim remains for local tooling
- Any orchestrator can now rely on explicit request correlation across CLI and API without changing match semantics.
