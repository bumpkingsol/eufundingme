from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import sentry_sdk

from .indexer import filter_indexable_grants
from .live_grant_cache import LiveGrantCache
from .models import GrantRecord, IndexStatus, MatchResponse


def build_match_path(status: IndexStatus, *, live_retrieval_capability: bool) -> str:
    if status.phase == "idle" and live_retrieval_capability:
        return "live_first"
    if status.phase in {"ready", "ready_degraded"} and status.matching_available:
        return "live_first" if live_retrieval_capability else "snapshot_only"
    return "unavailable"


def enrich_status(
    status: IndexStatus,
    *,
    openai_available: bool,
    live_retrieval_capability: bool,
) -> IndexStatus:
    return status.model_copy(
        update={
            "live_retrieval_available": live_retrieval_capability,
            "embeddings_available": openai_available,
            "ai_scoring_available": openai_available,
            "match_path": build_match_path(status, live_retrieval_capability=live_retrieval_capability),
        }
    )


def is_match_ready(status: IndexStatus) -> bool:
    return status.match_path in {"live_first", "snapshot_only"}


def prepare_match_grants(grants: Sequence[object], *, now: datetime) -> list[object]:
    if grants and all(isinstance(grant, GrantRecord) for grant in grants):
        return filter_indexable_grants(list(grants), now=now)
    return list(grants)


@dataclass(slots=True)
class CoordinatedMatchExecution:
    status: IndexStatus
    result_source: str
    all_grants: list[object]
    prepared_grants: list[object]
    match_response: MatchResponse


class MatchCoordinator:
    def __init__(
        self,
        *,
        app_state,
        match_service,
        translation_service,
        settings,
        live_grant_service=None,
        live_grant_cache: LiveGrantCache | None = None,
        live_retrieval_capability: bool = False,
    ) -> None:
        self.app_state = app_state
        self.match_service = match_service
        self.translation_service = translation_service
        self.settings = settings
        self.live_grant_service = live_grant_service
        self.live_grant_cache = live_grant_cache or LiveGrantCache()
        self.live_retrieval_capability = live_retrieval_capability

    def get_status(self) -> IndexStatus:
        return enrich_status(
            self.app_state.get_status(),
            openai_available=bool(getattr(self.settings, "openai_api_key", None)),
            live_retrieval_capability=self.live_retrieval_capability,
        )

    def execute_match(
        self,
        company_description: str,
        *,
        request_id: str | None,
        now: datetime | None = None,
    ) -> CoordinatedMatchExecution:
        reference_time = now or datetime.now(timezone.utc)
        status = self.get_status()
        live_result = None
        if self.live_grant_service is not None:
            live_result = self.live_grant_service.retrieve(
                company_description,
                now=reference_time,
            )

        all_grants = (live_result.grants if live_result is not None else []) or self.app_state.get_grants()
        prepared_grants = prepare_match_grants(all_grants, now=reference_time)
        base_reasons = list(live_result.degradation_reasons) if live_result is not None else []
        result_source = "live_retrieval" if live_result is not None and live_result.grants else "snapshot_fallback"
        if result_source == "snapshot_fallback":
            base_reasons.extend(status.degradation_reasons)

        has_ai_matching_capability = (
            status.embeddings_ready or status.embeddings_available or status.ai_scoring_available
        )
        if (
            not getattr(self.settings, "openai_api_key", None)
            and not has_ai_matching_capability
            and "lexical_only_mode" not in base_reasons
        ):
            base_reasons.append("lexical_only_mode")

        match_response = self.match_service.match(
            company_description,
            prepared_grants,
            now=reference_time,
            limit=self.settings.shortlist_limit,
            base_degradation_reasons=base_reasons,
        )
        match_response = self.translation_service.translate_match_response(match_response, all_grants)
        if result_source == "live_retrieval":
            self.live_grant_cache.store(
                request_id,
                [grant for grant in all_grants if isinstance(grant, GrantRecord)],
                now=reference_time,
            )
        sentry_sdk.set_measurement(
            "grant_embeddings_available",
            1.0 if (status.embeddings_ready or status.embeddings_available) else 0.0,
        )
        return CoordinatedMatchExecution(
            status=status,
            result_source=result_source,
            all_grants=list(all_grants),
            prepared_grants=prepared_grants,
            match_response=match_response,
        )
