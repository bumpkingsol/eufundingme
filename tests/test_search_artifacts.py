from datetime import datetime, timedelta, timezone

from backend.models import MatchResult
from backend.search_artifacts import SearchArtifactStore, build_locked_result_teaser


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
    )

    assert artifact.preview_result is not None
    assert artifact.preview_result.grant_id == "TOPIC-1"
    assert artifact.locked_result_count == 1


def test_search_artifact_store_prunes_expired_artifacts_on_get():
    store = SearchArtifactStore()
    created_at = datetime(2026, 4, 20, tzinfo=timezone.utc)
    artifact = store.create(
        fingerprint="fp-1",
        company_description="We build AI tools for Europe.",
        full_results=[make_result("TOPIC-1")],
        now=created_at,
        expires_in=timedelta(minutes=5),
    )

    assert store.get(artifact.id, now=created_at + timedelta(minutes=4)) is not None
    assert store.get(artifact.id, now=created_at + timedelta(minutes=5)) is None


def test_search_artifact_store_handles_zero_results():
    store = SearchArtifactStore()

    artifact = store.create(
        fingerprint="fp-1",
        company_description="We build AI tools for Europe.",
        full_results=[],
    )

    assert artifact.preview_result is None
    assert artifact.locked_results == []
    assert artifact.locked_result_count == 0
    assert artifact.full_results == []


def test_locked_result_teaser_omits_hidden_match_fields():
    teaser = build_locked_result_teaser(make_result("TOPIC-2", fit_score=84))

    payload = teaser.model_dump()
    assert payload == {
        "grant_id": "TOPIC-2",
        "title": "Grant TOPIC-2",
        "fit_score_band": "strong",
        "deadline": "2026-08-01",
        "budget": "EUR 6.2M",
    }
    assert "why_match" not in payload
    assert "application_angle" not in payload
    assert "portal_url" not in payload
