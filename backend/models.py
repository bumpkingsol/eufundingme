from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field


@dataclass(slots=True)
class GrantRecord:
    id: str
    title: str
    status: str
    portal_url: str
    deadline: str | None = None
    deadline_at: datetime | None = field(default=None, repr=False)
    budget_display: str | None = None
    budget_amount_eur: int | None = field(default=None, repr=False)
    keywords: list[str] = field(default_factory=list)
    framework_programme: str | None = None
    programme_division: str | None = None
    description: str | None = None
    call_identifier: str | None = None
    action_type: str | None = None
    search_text: str = ""

    def days_left(self, now: datetime | None = None) -> int | None:
        if self.deadline_at is None:
            return None
        reference = now or datetime.now(timezone.utc)
        return (self.deadline_at - reference).days

    def to_public_dict(self, now: datetime | None = None) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "deadline": self.deadline,
            "days_left": self.days_left(now=now),
            "budget": self.budget_display,
            "keywords": self.keywords,
            "framework_programme": self.framework_programme,
            "programme_division": self.programme_division,
            "call_identifier": self.call_identifier,
            "action_type": self.action_type,
            "portal_url": self.portal_url,
        }


@dataclass(slots=True)
class MatchCandidate:
    grant: GrantRecord
    shortlist_score: float


class MatchRequest(BaseModel):
    company_description: str = Field(min_length=20, max_length=5000)


class ProfileResolveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class ProfileResolveResponse(BaseModel):
    resolved: bool
    profile: str | None = None
    display_name: str | None = None
    source: str
    message: str | None = None


class MatchResult(BaseModel):
    grant_id: str
    title: str
    status: str
    deadline: str | None = None
    days_left: int | None = None
    budget: str | None = None
    portal_url: str
    fit_score: int
    why_match: str
    application_angle: str
    framework_programme: str | None = None
    programme_division: str | None = None
    keywords: list[str] = Field(default_factory=list)


class MatchResponse(BaseModel):
    indexed_grants: int
    results: list[MatchResult]


class IndexStatus(BaseModel):
    phase: str
    message: str
    indexed_grants: int = 0
    scanned_prefixes: int = 0
    total_prefixes: int = 0
    failed_prefixes: int = 0
    embeddings_ready: bool = False
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    matching_available: bool = False
    coverage_complete: bool = False
    truncated_prefixes: int = 0
    started_at: str | None = None
    finished_at: str | None = None


class HealthResponse(BaseModel):
    status: str


class ParsedLLMMatch(BaseModel):
    grant_id: str
    fit_score: int
    why_match: str
    application_angle: str


class ParsedLLMMatchList(BaseModel):
    matches: list[ParsedLLMMatch]
