# Production Gap Audit
**Date**: 2026-04-18  
**Codebase**: EU Grant Matcher (CLI + API + frontend)  
**Scope**: Full codebase behavior against autonomous-agent promise.

## Scope
Reviewed CLI matcher command contracts, API parity, index readiness semantics, installability path, and docs/entrypoint discoverability.

## Top Findings

### 1) Matching readiness is now explicitly blocked in API and CLI — good
`match` now uses a shared readiness gate and returns a structured `INDEX_NOT_READY` error when matching is unavailable. This closes a major drift point where partial/ongoing index states could previously produce best-effort output.

### 2) JSON-first machine contract is in place, but no request correlation yet
Both CLI and API now return machine-oriented errors with stable shape and exit codes for CLI. Missing request correlation (`request_id`) is still optional and currently not emitted, which limits distributed traceability for long-running autonomous jobs.

### 3) Installable script exists but depends on runtime context
`scripts/eufundingme` delegates to backend CLI and works when executed in the repo interpreter context. For globally installed usage, this should ideally become an installed console script to avoid interpreter/path drift.

### 4) Profile resolver path resilience is better but still environment-sensitive
Fallback path search exists and env override works, but behavior is still dependent on repo/package layout when running from unusual working directories. Existing resolver contract is acceptable for now but should be formalized with a documented package resource path to avoid surprises.

### 5) CLI exit/no-traceback behavior is acceptable
`run_match_query` wraps execution in try/except and converts failures to structured `INTERNAL_ERROR` payloads rather than traces. Input-validation failures through argparse already return clean non-zero exits.

## Recommendation
Production readiness is improved significantly and aligned with the CLI contract; remaining follow-up is to add request correlation IDs and package-level CLI installation (entry-point) for fully portable autonomous execution.
