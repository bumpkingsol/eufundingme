from backend.models import MatchResult
from backend.search_artifacts import SearchArtifactStore


def make_result(grant_id: str, *, fit_score: int = 92) -> MatchResult:
    return MatchResult(
        grant_id=grant_id,
        title=f"Grant {grant_id}",
        status="Open",
        portal_url=f"https://example.com/{grant_id}",
        fit_score=fit_score,
        why_match="Strong fit",
        application_angle="Lead with impact",
        deadline="2026-08-01",
        budget="EUR 6.2M",
    )


def test_search_artifact_store_returns_preview_and_locked_count():
    store = SearchArtifactStore()
    artifact = store.create(
        fingerprint="fp-1",
        company_description="We build AI tools for Europe.",
        full_results=[make_result("TOPIC-1"), make_result("TOPIC-2")],
        request_id="req-1",
    )

    assert artifact.preview_result is not None
    assert artifact.preview_result.grant_id == "TOPIC-1"
    assert artifact.locked_result_count == 1
