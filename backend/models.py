from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


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


class ProfileFromWebsiteRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("url must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("url must not be empty")
        if "://" not in normalized:
            return f"https://{normalized}"
        return normalized


class ProfileFromWebsiteResponse(BaseModel):
    resolved: bool
    profile: str | None = None
    display_name: str | None = None
    source: str
    normalized_url: str | None = None
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
    request_id: str | None = None
    indexed_grants: int
    refresh_indexed_grants: int = 0
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    results: list[MatchResult]


class IndexStatus(BaseModel):
    phase: str
    message: str
    indexed_grants: int = 0
    scanned_prefixes: int = 0
    total_prefixes: int = 0
    failed_prefixes: int = 0
    truncated_prefixes: int = 0
    embeddings_ready: bool = False
    degraded: bool = False
    coverage_complete: bool = False
    matching_available: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    current_prefix: str | None = None
    current_page: int | None = None
    pages_fetched: int = 0
    requests_completed: int = 0
    last_progress_at: str | None = None
    snapshot_loaded: bool = False
    snapshot_source: str | None = None
    snapshot_age_seconds: int | None = None
    refresh_in_progress: bool = False
    refresh_indexed_grants: int = 0
    summary: "IndexSummary | None" = None


class HealthResponse(BaseModel):
    status: str
    readiness_phase: str
    matching_available: bool
    degraded: bool


class ReadinessResponse(BaseModel):
    status: str
    phase: str
    message: str
    degraded: bool
    degradation_reasons: list[str] = Field(default_factory=list)
    snapshot_loaded: bool = False
    snapshot_source: str | None = None
    refresh_in_progress: bool = False


class ParsedLLMMatch(BaseModel):
    grant_id: str
    fit_score: int
    why_match: str
    application_angle: str


class ParsedLLMMatchList(BaseModel):
    matches: list[ParsedLLMMatch]


class IndexSummary(BaseModel):
    total_grants: int
    programme_count: int
    total_budget_eur: int
    total_budget_display: str | None = None
    closest_deadline: str | None = None
    closest_deadline_days: int | None = None


class GrantDeadline(BaseModel):
    label: str
    value: str


class GrantDocument(BaseModel):
    title: str
    url: str


class GrantDetailResponse(BaseModel):
    grant_id: str
    full_description: str = ""
    eligibility_criteria: list[str] = Field(default_factory=list)
    submission_deadlines: list[dict[str, str]] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    documents: list[dict[str, str]] = Field(default_factory=list)
    partner_search_available: bool | None = None
    source: str
    fallback_used: bool = False


class ApplicationBriefSections(BaseModel):
    company_fit_summary: str
    key_requirements: list[str] = Field(default_factory=list)
    suggested_consortium_partners: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    risks_and_gaps: list[str] = Field(default_factory=list)


class ApplicationBriefRequest(BaseModel):
    company_description: str = Field(min_length=20, max_length=5000)
    match_result: MatchResult
    grant_detail: GrantDetailResponse


class ApplicationBriefResponse(BaseModel):
    request_id: str | None = None
    markdown: str
    html: str
    sections: ApplicationBriefSections


@dataclass(slots=True)
class IndexBuildDetails:
    failed_prefixes: int = 0
    truncated_prefixes: int = 0
    degradation_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IndexBuildProgress:
    scanned_prefixes: int
    total_prefixes: int
    failed_prefixes: int
    indexed_grants: int
    current_prefix: str
    current_page: int
    pages_fetched: int
    requests_completed: int
    last_progress_at: str


class SnapshotEnvelope(BaseModel):
    grants: list[dict[str, object]]
    embeddings: dict[str, list[float]] = Field(default_factory=dict)
    status_payload: dict[str, object]
    written_at: str
