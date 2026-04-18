from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .app import create_app
from .app import build_match_unavailable_error, is_match_ready
from .models import IndexStatus


CLI_EXIT_SUCCESS = 0
CLI_EXIT_VALIDATION = 2
CLI_EXIT_TIMEOUT = 3
CLI_EXIT_RUNTIME = 1


def _build_match_error_payload(code: str, message: str, status: IndexStatus | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if status is not None:
        payload["error"]["status"] = status.model_dump()
    return payload


def _build_match_unavailable_payload(status: IndexStatus) -> dict[str, Any]:
    base = build_match_unavailable_error(status)
    return _build_match_error_payload(base["code"], base["message"], status)


def _build_match_timeout_payload(status: IndexStatus, timeout_seconds: float) -> dict[str, Any]:
    return _build_match_error_payload(
        "MATCH_TIMEOUT",
        f"Timed out after {timeout_seconds:.1f} seconds waiting for a ready index.",
        status,
    )


def _resolve_match_timeout(app) -> int:
    configured = getattr(app.state, "settings", None)
    if configured is not None and hasattr(configured, "cli_match_timeout_seconds"):
        return configured.cli_match_timeout_seconds
    return 60


def _wait_for_match_readiness(
    app_state,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[IndexStatus, bool, bool]:
    started_at = time.perf_counter()
    while True:
        status = app_state.get_status()
        if is_match_ready(status):
            return status, True, False

        if status.phase == "error" or status.phase == "ready":
            return status, False, False

        if timeout_seconds <= 0:
            return status, False, True

        if (time.perf_counter() - started_at) >= timeout_seconds:
            return status, False, True

        time.sleep(poll_interval_seconds)


def run_match_query(
    company_description: str,
    *,
    wait_timeout_seconds: float | None = None,
    poll_interval_seconds: float = 0.5,
) -> tuple[int, dict]:
    try:
        app = create_app()
        app.state.app_state.ensure_indexing_started()
        status = app.state.app_state.get_status()

        if wait_timeout_seconds is None:
            wait_timeout_seconds = _resolve_match_timeout(app)

        if not is_match_ready(status):
            # If the service reports ready but degraded, do not silently fall back to partial results.
            if status.phase == "ready":
                payload = _build_match_unavailable_payload(status)
                return CLI_EXIT_VALIDATION, payload

            status, ready, timed_out = _wait_for_match_readiness(
                app.state.app_state,
                timeout_seconds=wait_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            if not ready:
                if timed_out:
                    return CLI_EXIT_TIMEOUT, _build_match_timeout_payload(status, wait_timeout_seconds)
                return CLI_EXIT_VALIDATION, _build_match_unavailable_payload(status)

            status = app.state.app_state.get_status()

        grants = app.state.app_state.get_grants()
        result = app.state.match_service.match(
            company_description,
            grants,
            now=datetime.now(timezone.utc),
            limit=app.state.settings.shortlist_limit,
        )

        if isinstance(result, dict):
            indexed_grants = result.get("indexed_grants", 0)
            results = result.get("results", [])
        else:
            indexed_grants = result.indexed_grants
            results = result.model_dump()["results"]

        return CLI_EXIT_SUCCESS, {
            "ok": True,
            "indexed_grants": indexed_grants,
            "results": results,
            "status": status.model_dump(),
        }
    except Exception as exc:
        return CLI_EXIT_RUNTIME, _build_match_error_payload("INTERNAL_ERROR", str(exc))


def run_index_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    status = app.state.app_state.get_status()

    return status.model_dump()


def run_status_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    return app.state.app_state.get_status().model_dump()


def run_health_query() -> dict:
    return {"status": "ok"}


def run_profile_query(query: str) -> dict:
    app = create_app()
    resolution = app.state.profile_resolver.resolve(query)
    return {
        "resolved": resolution.resolved,
        "profile": resolution.profile,
        "display_name": resolution.display_name,
        "source": resolution.source,
        "message": resolution.message,
    }
