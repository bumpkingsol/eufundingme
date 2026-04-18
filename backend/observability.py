from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.openai import OpenAIIntegration

from .config import Settings

_SENTRY_INITIALIZED = False
_FILTERED = "[Filtered]"


def scrub_sentry_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    if "data" in request:
        request["data"] = _FILTERED

    headers = request.get("headers")
    if isinstance(headers, dict):
        for key in list(headers.keys()):
            if key.lower() in {"authorization", "cookie", "set-cookie"}:
                headers[key] = _FILTERED

    return event


def build_traces_sampler(default_rate: float) -> Callable[[dict[str, Any]], float]:
    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        transaction_context = sampling_context.get("transaction_context") or {}
        transaction_name = transaction_context.get("name") or ""
        if transaction_name in {
            "POST /api/match",
            "POST /api/profile/resolve",
            "POST /api/application-brief",
        }:
            return 1.0
        return default_rate

    return traces_sampler


def initialize_sentry(settings: Settings) -> None:
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED or not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[
            FastApiIntegration(),
            OpenAIIntegration(),
        ],
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        send_default_pii=settings.sentry_send_default_pii,
        before_send=scrub_sentry_event,
        traces_sampler=build_traces_sampler(settings.sentry_traces_sample_rate),
    )
    _SENTRY_INITIALIZED = True


def bind_request_context(
    *,
    operation: str,
    request_id: str,
    model: str | None = None,
) -> None:
    sentry_sdk.set_tag("operation", operation)
    sentry_sdk.set_tag("request_id", request_id)
    if model:
        sentry_sdk.set_tag("model", model)
    sentry_sdk.set_user({"id": request_id})
    sentry_sdk.set_context(
        "request_context",
        {
            "operation": operation,
            "request_id": request_id,
            "model": model,
        },
    )


def capture_backend_exception(
    exc: Exception,
    *,
    component: str,
    operation: str,
    model: str | None = None,
    request_id: str | None = None,
    fallback_used: bool = False,
    context: dict[str, Any] | None = None,
) -> None:
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("component", component)
        scope.set_tag("operation", operation)
        scope.set_tag("fallback_used", str(fallback_used).lower())
        if model:
            scope.set_tag("model", model)
        if request_id:
            scope.set_tag("request_id", request_id)
        if context:
            scope.set_context("backend_context", context)
        sentry_sdk.capture_exception(exc)
