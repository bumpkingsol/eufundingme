# Agentic CLI Robustness Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`[ ]`) syntax for tracking.

**Goal:** Make the CLI/API matcher path fully deterministic for autonomous agents and eliminate remaining execution risks.

**Architecture:** Keep CLI behavior aligned to API readiness and status contracts by routing both through shared helpers, then layer a tiny installable shim (`scripts/eufundingme`) as the preferred entrypoint.

**Tech Stack:** Python 3.12, FastAPI, argparse, subprocess-based test harness.

---

### Task 1: Production readiness hardening

- Files:
  - Modify: `backend/cli_services.py`
  - Modify: `backend/cli.py`
  - Test: `tests/cli/test_match_command.py`

- [x] Verify all match paths share one readiness decision.
- [x] Ensure `match` returns strict `ok=false` envelope with exit codes:
  - `2` for validation/readiness block
  - `3` for timeout
  - `1` for runtime failures
- [x] Keep default output in JSON mode and allow explicit `--text` mode only for humans.

### Task 2: Contract alignment and observability

- Files:
  - Modify: `backend/app.py`
  - Modify: `backend/config.py`
  - Test: `tests/test_api.py`

- [x] Align API `match` readiness to `status.matching_available` and reuse shared error shape (`MATCH_NOT_READY`).
- [x] Add config support for `OPENAI_PROFILE_EXPANSION_MODEL` and `CLI_MATCH_TIMEOUT_SECONDS`/`EUI_MATCH_TIMEOUT_SECONDS`.
- [x] Add unit tests for env-driven profile model and timeout parsing.

### Task 3: CLI discoverability and installable invocation

- Files:
  - Add: `scripts/eufundingme`
  - Modify: `README.md`
  - Modify: `frontend/index.html`
  - Tests: `tests/cli/test_cli_smoke.py`

- [x] Add installable shim that delegates to `backend.cli`.
- [x] Document fallback modes (`eufundingme ...` and `python -m backend.cli ...`).
- [x] Add frontend callout for explicit machine-first CLI JSON examples.

### Task 4: Remaining risks to close

- Files:
  - Add: `backend/cli.py` (request-id support, optional)
  - Add: `README.md`
  - Tests: `tests/cli/test_match_command.py`

- [ ] Add optional `request_id` in machine error envelopes when available.
- [ ] Add one explicit test for `index`/`status` field stability in CLI error path if future fields are added.

### Execution Checklist

- [x] Run CLI smoke checks:
  - `python -m backend.cli --help`
  - `python -m backend.cli health`
  - `python -m backend.cli status --json`
- [x] Run regression suite:
  - `python -m pytest -q`
- [ ] If any blocked/partial states remain untested, add integration coverage before release.
