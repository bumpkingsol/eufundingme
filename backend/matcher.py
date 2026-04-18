from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from openai import OpenAI

from .embeddings import lexical_shortlist
from .models import (
    GrantRecord,
    MatchCandidate,
    MatchResponse,
    MatchResult,
    ParsedLLMMatch,
    ParsedLLMMatchList,
)


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(value)))


class OpenAIScorer:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

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

        completion = self.client.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You rank EU grants for a company. Only use the provided candidates. "
                        "Return concise, concrete reasoning. Scores must be 0-100."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Company description:\n{company_description}\n\n"
                        "Candidate grants:\n"
                        f"{json.dumps(candidate_payload, ensure_ascii=True)}"
                    ),
                },
            ],
            response_format=ParsedLLMMatchList,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            return []
        return parsed.matches


class MatchService:
    def __init__(
        self,
        *,
        shortlister: Callable[[str, Sequence[GrantRecord], int], list[MatchCandidate]] | None = None,
        scorer: Callable[[str, Sequence[MatchCandidate]], Sequence[ParsedLLMMatch]] | None = None,
    ) -> None:
        self.shortlister = shortlister or (
            lambda company_description, grants, limit: lexical_shortlist(
                company_description,
                grants,
                limit=limit,
            )
        )
        self.scorer = scorer

    def match(
        self,
        company_description: str,
        grants: Sequence[GrantRecord],
        *,
        now: datetime | None = None,
        limit: int = 10,
        base_degradation_reasons: Sequence[str] | None = None,
    ) -> MatchResponse:
        reference_time = now or datetime.now(timezone.utc)
        degradation_reasons = list(base_degradation_reasons or [])
        candidates = self.shortlister(company_description, grants, limit)

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
                parsed_matches = list(self.scorer(company_description, candidates))
                results = build_ai_results(parsed_matches, candidates, now=reference_time)
                if results:
                    return MatchResponse(
                        indexed_grants=len(grants),
                        refresh_indexed_grants=len(grants),
                        degraded=bool(degradation_reasons),
                        degradation_reasons=degradation_reasons,
                        results=results,
                    )
            except Exception:
                if "openai_scoring_failed" not in degradation_reasons:
                    degradation_reasons.append("openai_scoring_failed")

        return MatchResponse(
            indexed_grants=len(grants),
            refresh_indexed_grants=len(grants),
            degraded=bool(degradation_reasons),
            degradation_reasons=degradation_reasons,
            results=build_fallback_results(company_description, candidates, now=reference_time),
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
    company_terms = set(company_description.lower().split())
    results: list[MatchResult] = []

    for candidate in candidates:
        grant = candidate.grant
        matched_keywords = [keyword for keyword in grant.keywords if keyword.lower() in company_terms]
        normalized_shortlist_score = candidate.shortlist_score
        if normalized_shortlist_score > 1:
            normalized_shortlist_score = min(normalized_shortlist_score / 5, 1)
        fallback_score = 70 + int(max(0.0, min(normalized_shortlist_score, 1.0)) * 20)
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
