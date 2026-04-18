from __future__ import annotations

from openai import OpenAI

from .config import Settings


def build_openai_client(settings: Settings) -> OpenAI | None:
    if not settings.openai_api_key:
        return None
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )


def build_reasoning(reasoning_effort: str | None) -> dict[str, str] | None:
    if not reasoning_effort:
        return None
    return {"effort": reasoning_effort}
