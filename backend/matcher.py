from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import sentry_sdk
from openai import OpenAI

from .embeddings import informative_terms, lexical_shortlist
from .models import (
    GrantRecord,
    MatchCandidate,
    MatchResponse,
    MatchResult,
    ParsedLLMMatch,
    ParsedLLMMatchList,
)
from .openai_client import build_reasoning


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(value)))


class OpenAIScorer:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: OpenAI | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)
        self.reasoning_effort = reasoning_effort

    def score(
        self,
        company_description: str,
        candidates: Sequence[MatchCandidate],
    ) -> list[ParsedLLMMatch]:
        candidate_payload = [
            {
                "grant_id": candidate.grant.id,
                "title": candidate.grant.title,
                "status": candidate.grant.status,
                "deadline": candidate.grant.deadline,
                "framework_programme": candidate.grant.framework_programme,
                "programme_division": candidate.grant.programme_division,
                "keywords": candidate.grant.keywords,
                "description": candidate.grant.description,
            }
            for candidate in candidates
        ]

        completion = self.client.responses.parse(
            model=self.model,
            instructions=(
                "You rank EU grants for a company. Only use the provided candidates. "
                "Return concise, concrete reasoning. Reference specific grant requirements, "
                "programme priorities, or keywords from the candidate grant and specific company capabilities "
                "from the input profile. Keep the guidance actionable. Scores must be 0-100."
            ),
            input=(
                f"Company description:\n{company_description}\n\n"
                "Candidate grants:\n"
                f"{json.dumps(candidate_payload, ensure_ascii=True)}"
            ),
            text_format=ParsedLLMMatchList,
            reasoning=build_reasoning(self.reasoning_effort),
        )
        parsed = completion.output_parsed
        if parsed is None:
            return []
        return parsed.matches


class MatchService:
    def __init__(
        self,
        *,
        shortlister: Callable[[str, Sequence[GrantRecord], int], list[MatchCandidate]] | None = None,
        scorer: Callable[[str, Sequence[MatchCandidate]], Sequence[ParsedLLMMatch]] | None = None,
        on_scorer_failure: Callable[[Exception], None] | Callable[..., None] | None = None,
    ) -> None:
        self.shortlister = shortlister or (
            lambda company_description, grants, limit: lexical_shortlist(
                company_description,
                grants,
                limit=limit,
            )
        )
        self.scorer = scorer
        self.on_scorer_failure = on_scorer_failure

    def match(
        self,
        company_description: str,
        grants: Sequence[GrantRecord],
        *,
        now: datetime | None = None,
        limit: int = 10,
        base_degradation_reasons: Sequence[str] | None = None,
    ) -> MatchResponse:
        started_at = time.perf_counter()
        reference_time = now or datetime.now(timezone.utc)
        degradation_reasons = list(base_degradation_reasons or [])
        try:
            with sentry_sdk.start_span(op="ai.shortlist", name="Candidate shortlist") as span:
                candidates = self.shortlister(company_description, grants, limit)
                span.set_data("grant_count", len(grants))
                span.set_data("candidate_count", len(candidates))

            if not candidates:
                return MatchResponse(
                    indexed_grants=len(grants),
                    refresh_indexed_grants=len(grants),
                    degraded=bool(degradation_reasons),
                    degradation_reasons=degradation_reasons,
                    results=[],
                )

            if self.scorer is not None:
                try:
                    with sentry_sdk.start_span(op="ai.score", name="LLM candidate scoring") as span:
                        span.set_data("candidate_count", len(candidates))
                        parsed_matches = list(self.scorer(company_description, candidates))
                        span.set_data("matches_returned", len(parsed_matches))
                    results = build_ai_results(parsed_matches, candidates, now=reference_time)
                    if results:
                        return MatchResponse(
                            indexed_grants=len(grants),
                            refresh_indexed_grants=len(grants),
                            degraded=bool(degradation_reasons),
                            degradation_reasons=degradation_reasons,
                            results=results,
                        )
                except Exception as exc:
                    if self.on_scorer_failure is not None:
                        self.on_scorer_failure(
                            exc,
                            context={
                                "candidate_count": len(candidates),
                                "grant_count": len(grants),
                                "fallback_used": True,
                            },
                        )
                    if "openai_scoring_failed" not in degradation_reasons:
                        degradation_reasons.append("openai_scoring_failed")

            return MatchResponse(
                indexed_grants=len(grants),
                refresh_indexed_grants=len(grants),
                degraded=bool(degradation_reasons),
                degradation_reasons=degradation_reasons,
                results=build_fallback_results(company_description, candidates, now=reference_time),
            )
        finally:
            sentry_sdk.set_measurement("grants_indexed", len(grants))
            sentry_sdk.set_measurement(
                "match_latency_ms",
                round((time.perf_counter() - started_at) * 1000, 3),
            )


def build_ai_results(
    parsed_matches: Sequence[ParsedLLMMatch],
    candidates: Sequence[MatchCandidate],
    *,
    now: datetime,
) -> list[MatchResult]:
    candidate_by_id = {candidate.grant.id: candidate for candidate in candidates}
    results: list[MatchResult] = []

    for parsed in parsed_matches:
        candidate = candidate_by_id.get(parsed.grant_id)
        if candidate is None:
            continue
        grant = candidate.grant
        results.append(
            MatchResult(
                grant_id=grant.id,
                title=grant.title,
                status=grant.status,
                deadline=grant.deadline,
                days_left=grant.days_left(now=now),
                budget=grant.budget_display,
                portal_url=grant.portal_url,
                fit_score=clamp_score(parsed.fit_score),
                why_match=parsed.why_match.strip(),
                application_angle=parsed.application_angle.strip(),
                framework_programme=grant.framework_programme,
                programme_division=grant.programme_division,
                keywords=grant.keywords,
            )
        )

    results.sort(key=lambda result: (-result.fit_score, result.days_left or 10_000, result.title))
    return results


def build_fallback_results(
    company_description: str,
    candidates: Sequence[MatchCandidate],
    *,
    now: datetime,
) -> list[MatchResult]:
    company_terms = informative_terms(company_description)
    results: list[MatchResult] = []

    for candidate in candidates:
        grant = candidate.grant
        matched_keywords = [
            keyword
            for keyword in grant.keywords
            if informative_terms(keyword) & company_terms
        ]
        overlap_count = max(0, int(round(candidate.shortlist_score)))
        fallback_score = 40 + min(overlap_count, 4) * 8
        why_match = (
            f"Matched on keywords: {', '.join(matched_keywords)}."
            if matched_keywords
            else f"Matched against grant themes in {grant.framework_programme or 'the current programme'}."
        )
        application_angle = (
            f"Lead with concrete European impact and fit with {grant.programme_division or grant.framework_programme or 'the programme priorities'}."
        )
        results.append(
            MatchResult(
                grant_id=grant.id,
                title=grant.title,
                status=grant.status,
                deadline=grant.deadline,
                days_left=grant.days_left(now=now),
                budget=grant.budget_display,
                portal_url=grant.portal_url,
                fit_score=clamp_score(fallback_score),
                why_match=why_match,
                application_angle=application_angle,
                framework_programme=grant.framework_programme,
                programme_division=grant.programme_division,
                keywords=grant.keywords,
            )
        )

    results.sort(key=lambda result: (-result.fit_score, result.days_left or 10_000, result.title))
    return results
