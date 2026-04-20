from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .models import LockedResultTeaser, MatchResult


def _fit_score_band(fit_score: int) -> str:
    if fit_score >= 90:
        return "excellent"
    if fit_score >= 75:
        return "strong"
    if fit_score >= 60:
        return "good"
    if fit_score >= 45:
        return "moderate"
    return "weak"


def build_locked_result_teaser(result: MatchResult) -> LockedResultTeaser:
    return LockedResultTeaser(
        grant_id=result.grant_id,
        title=result.title,
        fit_score_band=_fit_score_band(result.fit_score),
        deadline=result.deadline,
        budget=result.budget,
    )


@dataclass(slots=True)
class SearchArtifact:
    id: str
    fingerprint: str
    company_description: str
    preview_result: MatchResult | None
    locked_results: list[MatchResult]
    created_at: datetime
    expires_at: datetime

    @property
    def locked_result_count(self) -> int:
        return len(self.locked_results)

    @property
    def full_results(self) -> list[MatchResult]:
        if self.preview_result is None:
            return list(self.locked_results)
        return [self.preview_result, *self.locked_results]


class SearchArtifactStore:
    def __init__(self) -> None:
        self._artifacts: dict[str, SearchArtifact] = {}

    def create(
        self,
        *,
        fingerprint: str,
        company_description: str,
        full_results: list[MatchResult],
        request_id: str | None = None,
        now: datetime | None = None,
        expires_in: timedelta | None = None,
    ) -> SearchArtifact:
        reference_time = now or datetime.now(timezone.utc)
        ttl = expires_in or timedelta(days=7)
        preview_result = full_results[0] if full_results else None
        locked_results = list(full_results[1:]) if len(full_results) > 1 else []
        artifact = SearchArtifact(
            id=f"artifact-{uuid4().hex}",
            fingerprint=fingerprint,
            company_description=company_description,
            preview_result=preview_result,
            locked_results=locked_results,
            created_at=reference_time,
            expires_at=reference_time + ttl,
        )
        _ = request_id
        self._artifacts[artifact.id] = artifact
        return artifact

    def create_from_execution(
        self,
        *,
        fingerprint: str,
        company_description: str,
        execution,
        request_id: str | None = None,
        now: datetime | None = None,
        expires_in: timedelta | None = None,
    ) -> SearchArtifact:
        return self.create(
            fingerprint=fingerprint,
            company_description=company_description,
            full_results=list(execution.match_response.results),
            request_id=request_id,
            now=now,
            expires_in=expires_in,
        )

    def get(self, artifact_id: str) -> SearchArtifact | None:
        return self._artifacts.get(artifact_id)

