from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .app import create_app
from .app import build_match_unavailable_error, is_match_ready
from .models import IndexStatus
from .request_ids import resolve_request_id


CLI_EXIT_SUCCESS = 0
CLI_EXIT_VALIDATION = 2
CLI_EXIT_TIMEOUT = 3
CLI_EXIT_RUNTIME = 1


def _build_match_error_payload(
    code: str,
    message: str,
    status: IndexStatus | None = None,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if status is not None:
        payload["error"]["status"] = status.model_dump()
    if request_id is not None:
        payload["request_id"] = request_id
    return payload


def _build_match_unavailable_payload(
    status: IndexStatus,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    base = build_match_unavailable_error(status, request_id=request_id)
    return _build_match_error_payload(
        base["code"],
        base["message"],
        status,
        request_id=request_id,
    )


def _build_match_timeout_payload(
    status: IndexStatus,
    timeout_seconds: float,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    return _build_match_error_payload(
        "MATCH_TIMEOUT",
        f"Timed out after {timeout_seconds:.1f} seconds waiting for a ready index.",
        status,
        request_id=request_id,
    )


def _resolve_match_timeout(app) -> int:
    configured = getattr(app.state, "settings", None)
    if configured is not None and hasattr(configured, "cli_match_timeout_seconds"):
        return configured.cli_match_timeout_seconds
    return 60


def _get_match_coordinator(app):
    return getattr(getattr(app, "state", None), "match_coordinator", None)


def _normalize_status_for_legacy_path(status: IndexStatus) -> IndexStatus:
    if status.match_path != "unavailable":
        return status
    if status.phase in {"ready", "ready_degraded"} and status.matching_available:
        return status.model_copy(update={"match_path": "snapshot_only"})
    return status


def _wait_for_match_readiness(
    match_coordinator,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[IndexStatus, bool, bool]:
    started_at = time.perf_counter()
    while True:
        status = _normalize_status_for_legacy_path(match_coordinator.get_status())
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
    request_id: str | None = None,
) -> tuple[int, dict]:
    try:
        request_id = resolve_request_id(request_id)
        app = create_app()
        app.state.app_state.ensure_indexing_started()
        match_coordinator = _get_match_coordinator(app)
        status = (
            match_coordinator.get_status()
            if match_coordinator is not None
            else _normalize_status_for_legacy_path(app.state.app_state.get_status())
        )

        if wait_timeout_seconds is None:
            wait_timeout_seconds = _resolve_match_timeout(app)

        if not is_match_ready(status):
            # If the service reports ready but degraded, do not silently fall back to partial results.
            if status.phase == "ready":
                payload = _build_match_unavailable_payload(status, request_id=request_id)
                return CLI_EXIT_VALIDATION, payload

            status, ready, timed_out = _wait_for_match_readiness(
                match_coordinator or app.state.app_state,
                timeout_seconds=wait_timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            if not ready:
                if timed_out:
                    return CLI_EXIT_TIMEOUT, _build_match_timeout_payload(
                        status,
                        wait_timeout_seconds,
                        request_id=request_id,
                    )
                return CLI_EXIT_VALIDATION, _build_match_unavailable_payload(
                    status,
                    request_id=request_id,
                )

            status = (
                match_coordinator.get_status()
                if match_coordinator is not None
                else _normalize_status_for_legacy_path(app.state.app_state.get_status())
            )

        if match_coordinator is not None:
            execution = match_coordinator.execute_match(
                company_description,
                request_id=request_id,
                now=datetime.now(timezone.utc),
            )
            if isinstance(execution, dict):
                result = execution["match_response"]
                execution_status = execution["status"]
            else:
                result = execution.match_response
                execution_status = execution.status
            indexed_grants = result.indexed_grants
            results = result.model_dump()["results"]
            result_source = result.result_source
            payload_status = execution_status.model_dump()
        else:
            grants = app.state.app_state.get_grants()
            result = app.state.match_service.match(
                company_description,
                grants,
                limit=app.state.settings.shortlist_limit,
            )
            indexed_grants = result.indexed_grants
            results = result.model_dump()["results"]
            result_source = result.result_source
            payload_status = status.model_dump()

        return CLI_EXIT_SUCCESS, {
            "ok": True,
            "request_id": request_id,
            "indexed_grants": indexed_grants,
            "result_source": result_source,
            "results": results,
            "status": payload_status,
        }
    except Exception as exc:
        return CLI_EXIT_RUNTIME, _build_match_error_payload(
            "INTERNAL_ERROR",
            str(exc),
            request_id=request_id,
        )


def run_index_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    match_coordinator = _get_match_coordinator(app)
    status = (
        match_coordinator.get_status()
        if match_coordinator is not None
        else _normalize_status_for_legacy_path(app.state.app_state.get_status())
    )

    return status.model_dump()


def run_status_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    match_coordinator = _get_match_coordinator(app)
    status = (
        match_coordinator.get_status()
        if match_coordinator is not None
        else _normalize_status_for_legacy_path(app.state.app_state.get_status())
    )
    return status.model_dump()


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
