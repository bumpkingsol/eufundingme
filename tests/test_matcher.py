from datetime import datetime, timezone

from backend.embeddings import cosine_similarity, lexical_shortlist
from backend.matcher import MatchService
from backend.models import GrantRecord, MatchCandidate, ParsedLLMMatch


def make_grant(grant_id: str, title: str, *, keywords: list[str]) -> GrantRecord:
    return GrantRecord(
        id=grant_id,
        title=title,
        status="Open",
        portal_url=f"https://example.com/{grant_id}",
        deadline="2026-08-01",
        deadline_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        keywords=keywords,
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        search_text=f"{title} {' '.join(keywords)} horizon europe cluster 4".lower(),
    )


def test_cosine_similarity_returns_one_for_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_lexical_shortlist_prefers_overlap():
    grants = [
        make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"]),
        make_grant("TOPIC-2", "Battery Materials", keywords=["battery", "recycling"]),
    ]

    candidates = lexical_shortlist("We build AI safety tooling.", grants, limit=2)

    assert [candidate.grant.id for candidate in candidates] == ["TOPIC-1"]


def test_match_service_clamps_ai_scores():
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.9)
        ],
        scorer=lambda company_description, candidates: [
            ParsedLLMMatch(
                grant_id="TOPIC-1",
                fit_score=180,
                why_match="Strong overlap in applied AI safety.",
                application_angle="Lead with trusted deployment across Europe.",
            )
        ],
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].fit_score == 100


def test_match_service_falls_back_when_scorer_fails():
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.75)
        ],
        scorer=lambda company_description, candidates: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].grant_id == "TOPIC-1"
    assert response.results[0].fit_score >= 70
    assert "ai" in response.results[0].why_match.lower()
