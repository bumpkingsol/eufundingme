from __future__ import annotations

import os

import pytest

from backend.application_brief import ApplicationBriefService
from backend.config import load_settings
from backend.embeddings import EmbeddingService
from backend.matcher import OpenAIScorer
from backend.models import GrantDetailResponse, GrantRecord, MatchCandidate
from backend.openai_client import build_openai_client
from backend.profile_resolver import OpenAICompanyProfileExpander


pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_LIVE_SMOKE") != "1",
    reason="requires OPENAI_API_KEY and OPENAI_LIVE_SMOKE=1",
)


def test_openai_runtime_smoke() -> None:
    settings = load_settings()
    client = build_openai_client(settings)

    assert client is not None

    expander = OpenAICompanyProfileExpander(
        api_key=settings.openai_api_key or "",
        model=settings.openai_profile_expansion_model,
        client=client,
        reasoning_effort=settings.openai_profile_reasoning_effort,
    )
    expanded = expander.expand("OpenAI")
    assert expanded is not None
    display_name, profile = expanded
    assert display_name
    assert len(profile) > 40

    embedding_service = EmbeddingService(
        model=settings.openai_embedding_model,
        client=client,
    )
    embeddings = embedding_service.embed_texts(
        [
            "We build AI safety tooling for enterprise deployment across Europe.",
            "Battery manufacturing platforms for grid-scale storage.",
        ]
    )
    assert len(embeddings) == 2
    assert len(embeddings[0]) > 10

    grant = GrantRecord(
        id="TOPIC-SMOKE-1",
        title="Trustworthy AI deployment for European industry",
        status="Open",
        portal_url="https://example.com/TOPIC-SMOKE-1",
        deadline="2026-08-01",
        keywords=["ai", "safety", "deployment"],
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        description="Funding for safe and trustworthy AI deployment in European industry.",
        search_text="trustworthy ai deployment european industry safety",
    )
    scorer = OpenAIScorer(
        model=settings.openai_match_model,
        client=client,
        reasoning_effort=settings.openai_match_reasoning_effort,
    )
    scored = scorer.score(
        "We build AI safety tooling for enterprise deployment across Europe.",
        [MatchCandidate(grant=grant, shortlist_score=0.9)],
    )
    assert scored
    assert scored[0].grant_id == "TOPIC-SMOKE-1"

    brief_service = ApplicationBriefService(
        client=client,
        model=settings.openai_match_model,
        reasoning_effort=settings.openai_match_reasoning_effort,
    )
    brief = brief_service.generate(
        company_description="We build AI safety tooling for enterprise deployment across Europe.",
        match_result={
            "grant_id": "TOPIC-SMOKE-1",
            "title": grant.title,
            "status": grant.status,
            "deadline": grant.deadline,
            "days_left": None,
            "budget": "EUR 4M",
            "portal_url": grant.portal_url,
            "fit_score": 85,
            "why_match": "Strong overlap in trustworthy AI deployment.",
            "application_angle": "Lead with safe enterprise deployment and European impact.",
            "framework_programme": grant.framework_programme,
            "programme_division": grant.programme_division,
            "keywords": grant.keywords,
        },
        grant_detail=GrantDetailResponse(
            grant_id="TOPIC-SMOKE-1",
            full_description="Long-form topic detail for trustworthy AI deployment in Europe.",
            eligibility_criteria=["EU legal entity", "Industrial deployment focus"],
            submission_deadlines=[{"label": "Main deadline", "value": "2026-08-01"}],
            expected_outcomes=["Trusted deployment outcomes"],
            documents=[],
            partner_search_available=True,
            source="smoke",
            fallback_used=False,
        ).model_dump(),
    )
    assert "application brief" in brief.markdown.lower()
