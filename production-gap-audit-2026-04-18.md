# Production Gap Audit
**Date**: 2026-04-18
**Codebase**: EU Grant Matcher — FastAPI backend with vanilla HTML/CSS/JS frontend, plus OpenAI and EU Commission API integrations.
**Scope**: Full codebase audit (47 files). Prioritized critical user flows in frontend matching/indexing, indexing pipeline, and model/API contracts. Excluded: vendored files, `.pytest_cache` artifacts, virtualenv.
**Stack**: Python (FastAPI, Pydantic, Requests, OpenAI, Sentry) + Vanilla JavaScript frontend.
**Mode**: Quick (Phases 2+5 completed; 2.9 validated via call-site contract checks). Full repo no git history available in this workspace.

## Executive Summary
The app has a useful architecture for web matching flows, but several production gaps could break user trust during real usage. The highest risks are around silent degraded states: indexing can report `ready` while yielding zero or partial grants, and frontend/backend status contracts are drifting. The current code also lacks an explicit CLI entrypoint despite your requirement, so non-UI agent use is not supported yet.

## Critical Findings

### CLI Mode Missing Despite User Requirement
- **Location**: Entire repository; no command interface in `backend/` or `frontend/`; entrypoint is only `backend.app:app` in docs.
- **What happens**: Teams trying to use this from automation (Openclaw, Hermes, or CLI-driven agents) have no way to invoke matching, indexing, or profile resolution without spinning up HTTP server + HTTP client wrappers manually.
- **Why it matters**: Blocks the explicitly requested use case (“agent tools can call CLI”), increases integration complexity, and increases runtime mismatch (agent expects deterministic, scriptable output).
- **Confidence**: High — traced full code paths: routing is only HTTP endpoints in `backend/app.py`, and there is no `if __name__ == '__main__'`, `argparse`, `click`, or `typer` usage.
- **How to verify**: Try `python backend/app.py` or search for CLI parser in repo; confirm only server startup works.
- **Recommended fix**: Add a dedicated CLI entrypoint module (e.g., `backend/cli.py`) with commands for indexing, matching, profile resolution, and health checks; output structured JSON for agents.
- **Evidence**: `rg` for CLI terms returned no CLI artifacts. `backend/app.py` only exposes FastAPI routes.

### Partial Index Can Surface as Ready Without Quality Signal
- **Location**: `backend/indexer.py:96` + `backend/state.py:54-96` + `frontend/app.js:132`.
- **What happens**: Prefix fetch failures are swallowed per prefix and overall indexing still ends `ready` even when many prefixes failed.
- **Why it matters**: Users are enabled to run matching while grant corpus is partial/empty; results become weak or wrong with little explanation.
- **Confidence**: High — call path traced from prefix-level exception handling → index build completion → status `phase="ready"` → frontend enables matching on `phase === "ready"`.
- **How to verify**: Simulate EC client exceptions for all prefixes and observe `/api/index/status` returning ready, then run `/api/match`.
- **Recommended fix**: Track failure ratio and expose a `degraded`/`partially_ready` status with blocked matching or explicit degraded badge and explicit reason list.
- **Evidence**: `except Exception:` per prefix in indexer and unconditional success assignment in state.

### API Contract Drift Hides Frontend/Status Reality
- **Location**: `backend/models.py:64-68` + `frontend/app.js:146-170`.
- **What happens**: Frontend expects fields like `degradation_reasons`, `matching_available`, `coverage_complete`, `truncated_prefixes` that are not guaranteed by backend schema.
- **Why it matters**: Status UX is inconsistent, and agent-facing scripts consuming status cannot rely on contract stability.
- **Confidence**: High — direct schema check against `IndexStatus` model and frontend reads.
- **How to verify**: Call `/api/index/status`, inspect payload against JS code's status assumptions.
- **Recommended fix**: Extend `IndexStatus` to match actual frontend and CLI needs, or simplify frontend to consume only declared fields.
- **Evidence**: Frontend accesses non-schema keys and uses fallback values.

## High Severity

### Swallowed exceptions hide degraded state and reduce observability
- **Location**: `backend/app.py:61-63`, `backend/matcher.py:117`, `backend/state.py:77-79`, `backend/indexer.py:112`.
- **What happens**: Core compute paths swallow failures and fall back silently.
- **Why it matters**: Hard to know whether failures are data-quality issues vs infra issues; agent users may receive poor results with no actionable feedback.
- **Confidence**: Medium — behavior is clear by inspection; user-facing impact inferred from fallback UX.
- **How to verify**: Force OpenAI/API errors via monkeypatch and confirm no error indicator is surfaced beyond lower-scoring fallback results.
- **Recommended fix**: Add warning channel fields (`degraded`, reasons, retry hints) and structured logs/metrics.

### Missing/incomplete profile metadata source path
- **Location**: `backend/profile_resolver.py:10`.
- **What happens**: Demo profiles file path points outside expected package root (`parents[2]`).
- **Why it matters**: Name-only company inputs in non-repo working dirs resolve inconsistently.
- **Confidence**: High — code hard-codes relative path and no fallback path strategy.
- **How to verify**: Run from installed package context and call `/api/profile/resolve` with known demo name.
- **Recommended fix**: Use package-local resource loading or configurable env path.

### Hard-coded PII capture setting in observability
- **Location**: `backend/app.py:29`.
- **What happens**: Sentry configured with `send_default_pii=True`.
- **Why it matters**: Company descriptions/profile text entered by users can cross into observability unless explicitly desired.
- **Confidence**: High.
- **How to verify**: Induce error with company text and inspect captured event fields.
- **Recommended fix**: Default to minimizing PII and make PII capture opt-in.

## Medium Severity

### Profile/profile expansion model hard-coded/default mismatch
- **Location**: `backend/config.py:27-29` and `backend/profile_resolver.py:30-35`.
- **What happens**: Matching model is configurable; profile expansion model is hard-coded.
- **Why it matters**: Drift in cost/reliability expectations and inconsistent runtime controls.
- **Confidence**: Medium.
- **How to verify**: Compare env var controls and code defaults.
- **Recommended fix**: Unify model config into Settings and docs.

### Frontend messaging/feature discoverability does not call out CLI path
- **Location**: `frontend/index.html` hero/CTA sections; no CLI messaging.
- **What happens**: Users only see web workflow and may not discover non-UI interface.
- **Why it matters**: Fails your production requirement to make CLI option explicit to end users/agents.
- **Confidence**: High.
- **How to verify**: Inspect hero and submit hints; confirm no CLI mention.
- **Recommended fix**: Add short CLI usage section and link to command docs.

## Low Severity

### Missing dependency bootstrapping in docs and setup consistency
- **Location**: `.env.example` and README install/run instructions vs implementation settings.
- **What happens**: Optional settings and debug flags are documented inconsistently.
- **Why it matters**: Friction in non-developer agent usage and reproducibility.
- **Confidence**: Medium.
- **Recommended fix**: Expand docs to include all supported env vars and optional behaviors.

## Claimed vs. Actual Capability Matrix
| Capability (from docs/README) | Status | Notes |
|-------------------------------|--------|-------|
| Match EU grants via web flow | Working | Backend + frontend endpoints exist and are functionally connected. |
| Index grants in background at startup | Partial | Indexing starts, but degraded/pool coverage errors can still be marked as ready. |
| AI + lexical fallback when scoring fails | Working | Fallback is present, but lacks explicit user-visible degraded state. |
| Frontend explicit CLI usage | Missing | No CLI entrypoint is currently exposed. |
| Health endpoint for monitoring | Working | `/api/health` exists; no dedicated process lifecycle checks around background task state. |
| Profile resolution by short query | Working | Endpoint exists; demo profile resolution depends on external file path and optional OpenAI. |

## Positive Observations
- Clear separation between normalization/matching/indexing/services in backend modules.
- Defensive fallback behavior means matching still returns data even when optional AI features fail.
- API schemas are mostly centralized in `backend/models.py`.
- Frontend status polling and disabled-state logic already exists, so adding explicit degraded modes is incremental.

## Methodology
- Ran reconnaissance over README, config, environment docs, backend/frontend source, and tests.
- Used parallel parallelization for broad sweep across silent failures, implementation completeness, integration/contracts, UX/security/performance/observability.
- Used grep/pattern scans for swallowed errors, stub markers, env/API route mismatches, and status contract fields.
- Cross-checked backend `IndexStatus` schema against frontend expectations.
- Attempted test execution: `python -m pytest -q tests` failed due missing packages (`fastapi`, `requests`, `openai`, `pydantic`) in the current interpreter.
