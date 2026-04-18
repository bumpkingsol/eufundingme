from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import create_app
from backend.config import Settings
from backend.live_grants import LiveGrantRetrievalResult
from backend.models import (
    GrantRecord,
    ApplicationBriefResponse,
    GrantDetailResponse,
    IndexStatus,
    IndexSummary,
    MatchResponse,
    MatchResult,
    ProfileFromWebsiteRequest,
)


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "readiness_phase": "ready_degraded",
        "matching_available": True,
        "degraded": True,
    }


def test_health_endpoint_reports_readiness_state():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Index ready with degraded coverage",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=1,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=True,
                coverage_complete=False,
                matching_available=True,
                degradation_reasons=["prefix_fetch_failed", "lexical_only_mode"],
                snapshot_loaded=True,
                snapshot_source="runtime",
                snapshot_age_seconds=120,
                refresh_in_progress=True,
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "readiness_phase": "ready_degraded",
        "matching_available": True,
        "degraded": True,
    }


def test_root_route_serves_frontend_shell():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Find EU funding for your company in 30 seconds." in response.text
    assert 'rel="icon"' in response.text
    assert 'id="resolution-banner"' in response.text
    assert 'id="quick-fill-openai"' in response.text
    assert "Try OpenAI" in response.text
    assert "novalidate" in response.text
    assert "status-failures" in response.text
    assert "status-coverage" in response.text


def test_favicon_route_exists():
    client = TestClient(create_app())

    response = client.get("/favicon.ico")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"


def test_index_status_endpoint_starts_indexing_and_returns_status():
    class FakeState:
        def __init__(self) -> None:
            self.started = False

        def ensure_indexing_started(self) -> None:
            self.started = True

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="building",
                message="Indexing grants",
                indexed_grants=12,
                scanned_prefixes=4,
                total_prefixes=10,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=False,
                coverage_complete=False,
                matching_available=False,
                degradation_reasons=[],
                current_prefix="HORIZON-CL4-2026",
                current_page=2,
                pages_fetched=8,
                requests_completed=8,
                last_progress_at="2026-04-18T10:00:00+00:00",
            )

        def get_grants(self) -> list[object]:
            return []

        def get_index_summary(self) -> IndexSummary:
            return IndexSummary(
                total_grants=12,
                programme_count=3,
                total_budget_eur=9_000_000,
                total_budget_display="EUR 9.0M",
                closest_deadline="2026-08-01",
                closest_deadline_days=14,
            )

    app = create_app(app_state=FakeState())
    client = TestClient(app)

    response = client.get("/api/index/status")

    assert response.status_code == 200
    assert response.json()["phase"] == "building"
    assert response.json()["current_prefix"] == "HORIZON-CL4-2026"
    assert response.json()["summary"]["programme_count"] == 3
    assert app.state.app_state.started is True


def test_readiness_endpoint_reports_snapshot_backed_matching():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Using saved index while live refresh runs",
                indexed_grants=12,
                scanned_prefixes=1,
                total_prefixes=10,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=True,
                degraded=True,
                coverage_complete=False,
                matching_available=True,
                degradation_reasons=["stale_snapshot_mode"],
                snapshot_loaded=True,
                snapshot_source="runtime",
                snapshot_age_seconds=90,
                refresh_in_progress=True,
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["snapshot_loaded"] is True
    assert response.json()["snapshot_source"] == "runtime"
    assert response.json()["refresh_in_progress"] is True


def test_readiness_endpoint_reports_bundled_seed_matching():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Using bundled seed snapshot while live refresh runs",
                indexed_grants=12,
                scanned_prefixes=0,
                total_prefixes=10,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=True,
                degraded=True,
                coverage_complete=False,
                matching_available=True,
                degradation_reasons=["bundled_seed_mode"],
                snapshot_loaded=True,
                snapshot_source="bundled",
                snapshot_age_seconds=90,
                refresh_in_progress=True,
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["snapshot_loaded"] is True
    assert response.json()["snapshot_source"] == "bundled"


def test_readiness_endpoint_reports_live_retrieval_capabilities():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="idle",
                message="Snapshot cache unavailable",
                indexed_grants=0,
                scanned_prefixes=0,
                total_prefixes=0,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=False,
                coverage_complete=False,
                matching_available=False,
                degradation_reasons=[],
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["live_retrieval_available"] is True


def test_match_endpoint_returns_ranked_results():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Ready",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=0,
                embeddings_ready=True,
                truncated_prefixes=0,
                degraded=True,
                coverage_complete=True,
                matching_available=True,
                degradation_reasons=["openai_scoring_failed"],
            )

        def get_grants(self) -> list[object]:
            return ["placeholder"]

    class FakeMatchService:
        def match(
            self,
            company_description: str,
            grants: list[object],
            now=None,
            limit: int = 10,
            base_degradation_reasons=None,
        ) -> MatchResponse:
            assert company_description == "We build AI safety tooling across Europe."
            assert grants == ["placeholder"]
            assert base_degradation_reasons == ["openai_scoring_failed"]
            return MatchResponse(
                indexed_grants=32,
                degraded=True,
                degradation_reasons=["openai_scoring_failed"],
                results=[
                    MatchResult(
                        grant_id="TOPIC-1",
                        title="AI Safety Grant",
                        status="Open",
                        deadline="2026-08-01",
                        days_left=105,
                        budget="EUR 6.2M",
                        portal_url="https://example.com/TOPIC-1",
                        fit_score=92,
                        why_match="Strong overlap in AI safety deployment.",
                        application_angle="Lead with trusted deployment across Europe.",
                        framework_programme="Horizon Europe",
                        programme_division="Cluster 4",
                        keywords=["ai", "safety"],
                    )
                ],
            )

    client = TestClient(create_app(app_state=FakeState(), match_service=FakeMatchService()))

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["grant_id"] == "TOPIC-1"
    assert response.json()["results"][0]["fit_score"] == 92
    assert response.json()["degraded"] is True
    assert response.json()["degradation_reasons"] == ["openai_scoring_failed"]


def test_match_endpoint_returns_translated_non_english_results():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready",
                message="Ready",
                indexed_grants=1,
                scanned_prefixes=1,
                total_prefixes=1,
                failed_prefixes=0,
                embeddings_ready=True,
                truncated_prefixes=0,
                degraded=False,
                coverage_complete=True,
                matching_available=True,
                degradation_reasons=[],
            )

        def get_grants(self) -> list[object]:
            from backend.models import GrantRecord

            return [
                GrantRecord(
                    id="TOPIC-BG",
                    title="Национална програма за иновации",
                    status="Open",
                    portal_url="https://example.com/TOPIC-BG",
                    source_language="bg",
                    description="Програма за България",
                    keywords=["innovation"],
                    search_text="innovation",
                )
            ]

    class FakeMatchService:
        def match(self, company_description: str, grants: list[object], now=None, limit: int = 10, base_degradation_reasons=None) -> MatchResponse:
            return MatchResponse(
                indexed_grants=1,
                results=[
                    MatchResult(
                        grant_id="TOPIC-BG",
                        title="Национална програма за иновации",
                        status="Open",
                        portal_url="https://example.com/TOPIC-BG",
                        fit_score=88,
                        why_match="Strong fit",
                        application_angle="Lead with deployment",
                        keywords=[],
                    )
                ],
            )

    class FakeTranslationService:
        def translate_match_response(self, response, grants):
            return response.model_copy(
                update={
                    "results": [
                        response.results[0].model_copy(
                            update={
                                "title": "National innovation programme",
                                "source_language": "bg",
                                "translated_from_source": True,
                                "translation_note": "Translated from Bulgarian. This grant appears tied to Bulgaria.",
                            }
                        )
                    ]
                }
            )

        def translate_grant_detail(self, detail, grant=None):
            return detail

    app = create_app(app_state=FakeState(), match_service=FakeMatchService())
    app.state.translation_service = FakeTranslationService()
    client = TestClient(app)

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["title"] == "National innovation programme"
    assert payload["results"][0]["source_language"] == "bg"
    assert payload["results"][0]["translated_from_source"] is True
    assert "Bulgaria" in payload["results"][0]["translation_note"]


def test_match_endpoint_prefers_live_retrieval_and_reports_result_source():
    live_grant = GrantRecord(
        id="LIVE-1",
        title="Live AI Grant",
        status="Open",
        portal_url="https://example.com/LIVE-1",
        deadline="2026-08-01",
        deadline_at=datetime.fromisoformat("2026-08-01T17:00:00+00:00"),
        keywords=["ai", "safety"],
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        search_text="live ai grant ai safety",
    )

    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Snapshot cache ready",
                indexed_grants=32,
                scanned_prefixes=0,
                total_prefixes=0,
                failed_prefixes=0,
                embeddings_ready=False,
                truncated_prefixes=0,
                degraded=True,
                coverage_complete=False,
                matching_available=True,
                degradation_reasons=["stale_snapshot_mode"],
                snapshot_loaded=True,
                snapshot_source="runtime",
            )

        def get_grants(self) -> list[object]:
            return ["snapshot-grant"]

    class FakeLiveGrantService:
        def retrieve(self, company_description: str, *, now=None):
            assert company_description == "We build AI safety tooling across Europe."
            return LiveGrantRetrievalResult(grants=[live_grant], queries=["artificial intelligence"])

    class FakeMatchService:
        def match(
            self,
            company_description: str,
            grants: list[object],
            now=None,
            limit: int = 10,
            base_degradation_reasons=None,
        ) -> MatchResponse:
            assert grants == [live_grant]
            assert "stale_snapshot_mode" not in (base_degradation_reasons or [])
            return MatchResponse(
                indexed_grants=1,
                degraded=False,
                degradation_reasons=[],
                results=[
                    MatchResult(
                        grant_id="LIVE-1",
                        title="Live AI Grant",
                        status="Open",
                        portal_url="https://example.com/LIVE-1",
                        fit_score=90,
                        why_match="Strong live fit.",
                        application_angle="Lead with deployment.",
                        keywords=["ai", "safety"],
                    )
                ],
            )

    client = TestClient(
        create_app(
            app_state=FakeState(),
            match_service=FakeMatchService(),
            live_grant_service=FakeLiveGrantService(),
        )
    )

    response = client.post("/api/match", json={"company_description": "We build AI safety tooling across Europe."})

    assert response.status_code == 200
    assert response.json()["result_source"] == "live_retrieval"


def test_readiness_endpoint_distinguishes_usable_matching():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="building",
                message="Indexing grants",
                indexed_grants=3,
                scanned_prefixes=2,
                total_prefixes=10,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=False,
                coverage_complete=False,
                matching_available=False,
                degradation_reasons=[],
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_match_endpoint_allows_ready_degraded_state():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready_degraded",
                message="Index ready with degraded quality",
                indexed_grants=1,
                scanned_prefixes=1,
                total_prefixes=1,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=True,
                coverage_complete=True,
                matching_available=True,
                degradation_reasons=["lexical_only_mode"],
            )

        def get_grants(self) -> list[object]:
            return ["placeholder"]

    class FakeMatchService:
        def match(
            self,
            company_description: str,
            grants: list[object],
            now=None,
            limit: int = 10,
            base_degradation_reasons=None,
        ) -> MatchResponse:
            return MatchResponse(indexed_grants=1, degraded=True, degradation_reasons=["lexical_only_mode"], results=[])

    client = TestClient(create_app(app_state=FakeState(), match_service=FakeMatchService()))

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
    )

    assert response.status_code == 200
    assert response.json()["degraded"] is True


def test_match_endpoint_blocks_when_matching_unavailable():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready",
                message="Ready but degraded",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=0,
                embeddings_ready=True,
                matching_available=False,
                degraded=True,
                coverage_complete=True,
                degradation_reasons=["partial_coverage"],
            )

        def get_grants(self) -> list[object]:
            return ["placeholder"]

    app = create_app(app_state=FakeState(), match_service=None)
    client = TestClient(app)

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["code"] == "INDEX_NOT_READY"
    assert "request_id" in payload["detail"]
    assert payload["detail"]["status"]["phase"] == "ready"


def test_match_endpoint_includes_request_id_header_override():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self):
            return IndexStatus(
                phase="ready",
                message="Ready but degraded",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=0,
                embeddings_ready=True,
                matching_available=False,
                degraded=True,
                coverage_complete=True,
                degradation_reasons=["partial_coverage"],
            )

        def get_grants(self):
            return ["placeholder"]

    client = TestClient(create_app(app_state=FakeState(), match_service=None))

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
        headers={"X-Request-ID": "agent-run-override"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["request_id"] == "agent-run-override"


def test_match_endpoint_records_truthful_embedding_measurements(monkeypatch):
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self) -> IndexStatus:
            return IndexStatus(
                phase="ready",
                message="Ready",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=True,
                degraded=False,
                coverage_complete=True,
                matching_available=True,
                degradation_reasons=[],
            )

        def get_grants(self) -> list[object]:
            return ["placeholder"]

    class FakeMatchService:
        def match(
            self,
            company_description: str,
            grants: list[object],
            now=None,
            limit: int = 10,
            base_degradation_reasons=None,
        ) -> MatchResponse:
            return MatchResponse(indexed_grants=32, degraded=False, degradation_reasons=[], results=[])

    measurements = []
    monkeypatch.setattr(
        "backend.app.sentry_sdk.set_measurement",
        lambda name, value: measurements.append((name, value)),
    )

    client = TestClient(create_app(app_state=FakeState(), match_service=FakeMatchService()))

    response = client.post(
        "/api/match",
        json={"company_description": "We build AI safety tooling across Europe."},
    )

    assert response.status_code == 200
    assert ("grant_embeddings_available", 1.0) in measurements


def test_sentry_debug_route_exists():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/sentry-debug")

    assert response.status_code == 500


def test_profile_resolve_endpoint_returns_demo_profile():
    client = TestClient(create_app())

    response = client.post("/api/profile/resolve", json={"query": "OpenAI"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolved"] is True
    assert payload["display_name"] == "OpenAI"
    assert payload["source"] == "demo_profile"


def test_profile_resolve_endpoint_returns_unresolved_without_match():
    class FakeResolver:
        def resolve(self, query: str):
            class Resolution:
                resolved = False
                profile = None
                display_name = None
                source = "unresolved"
                message = "Add one or two sentences about what the company does."

            return Resolution()

    client = TestClient(create_app(profile_resolver=FakeResolver()))

    response = client.post("/api/profile/resolve", json={"query": "Acme"})

    assert response.status_code == 200
    assert response.json() == {
        "resolved": False,
        "profile": None,
        "display_name": None,
        "source": "unresolved",
        "message": "Add one or two sentences about what the company does.",
    }


def test_profile_from_website_request_normalizes_and_validates_url():
    request = ProfileFromWebsiteRequest(url="  sentry.io  ")

    assert request.url == "https://sentry.io"


def test_profile_from_website_request_rejects_whitespace_only_input():
    with pytest.raises(ValueError):
        ProfileFromWebsiteRequest(url="   ")


@pytest.mark.parametrize("value", [123, None])
def test_profile_from_website_request_rejects_non_string_input(value):
    with pytest.raises(ValidationError):
        ProfileFromWebsiteRequest(url=value)


def test_profile_from_website_endpoint_returns_generated_profile():
    class FakeWebsiteProfileService:
        def resolve(self, url: str):
            assert url == "https://sentry.io"
            from backend.models import ProfileFromWebsiteResponse

            return ProfileFromWebsiteResponse(
                resolved=True,
                profile="Sentry builds developer observability tooling.",
                display_name="Sentry",
                source="website_profile",
                normalized_url="https://sentry.io",
            )

    app = create_app()
    app.state.website_profile_service = FakeWebsiteProfileService()
    client = TestClient(app)

    response = client.post("/api/profile/from-website", json={"url": "sentry.io"})

    assert response.status_code == 200
    assert response.json() == {
        "resolved": True,
        "profile": "Sentry builds developer observability tooling.",
        "display_name": "Sentry",
        "source": "website_profile",
        "normalized_url": "https://sentry.io",
        "message": None,
    }


def test_profile_from_website_endpoint_reports_service_failure():
    class FailingWebsiteProfileService:
        def resolve(self, url: str):
            assert url == "https://sentry.io"
            raise RuntimeError("website profile generation failed")

    app = create_app()
    app.state.website_profile_service = FailingWebsiteProfileService()
    client = TestClient(app)

    response = client.post("/api/profile/from-website", json={"url": "sentry.io"})

    assert response.status_code == 502
    assert response.json()["detail"]["message"] == "website profile generation failed"
    assert "request_id" in response.json()["detail"]


def test_profile_from_website_endpoint_returns_503_when_service_unavailable():
    app = create_app()
    app.state.website_profile_service = None
    client = TestClient(app)

    response = client.post("/api/profile/from-website", json={"url": "sentry.io"})

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "website profile service unavailable"
    assert "request_id" in response.json()["detail"]


def test_match_endpoint_keeps_short_description_validation():
    client = TestClient(create_app())

    response = client.post("/api/match", json={"company_description": "OpenAI"})

    assert response.status_code == 422


def test_application_brief_endpoint_returns_markdown_and_sections():
    class FakeBriefService:
        def generate(self, *, company_description, match_result, grant_detail):
            assert company_description == "We build AI tools for industrial companies."
            assert match_result["grant_id"] == "TOPIC-1"
            assert grant_detail["grant_id"] == "TOPIC-1"
            return ApplicationBriefResponse(
                markdown="# Application brief",
                html="<article>Application brief</article>",
                sections={
                    "company_fit_summary": "Strong fit",
                    "key_requirements": ["Requirement 1"],
                    "suggested_consortium_partners": ["Partner 1"],
                    "timeline": ["Week 1"],
                    "risks_and_gaps": ["Need pilot customer"],
                },
            )

    app = create_app()
    app.state.application_brief_service = FakeBriefService()
    client = TestClient(app)

    response = client.post(
        "/api/application-brief",
        headers={"X-Request-ID": "journey-123"},
        json={
            "company_description": "We build AI tools for industrial companies.",
            "match_result": {
                "grant_id": "TOPIC-1",
                "title": "AI Grant",
                "status": "Open",
                "portal_url": "https://example.com/TOPIC-1",
                "fit_score": 90,
                "why_match": "Strong fit",
                "application_angle": "Lead with deployment outcomes",
                "keywords": ["ai"],
            },
            "grant_detail": {
                "grant_id": "TOPIC-1",
                "full_description": "Long description",
                "eligibility_criteria": ["EU legal entity"],
                "submission_deadlines": [{"label": "Main deadline", "value": "2026-08-01"}],
                "expected_outcomes": ["Outcome 1"],
                "documents": [],
                "partner_search_available": True,
                "source": "browser_topic_detail",
                "fallback_used": False,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "journey-123"
    assert payload["markdown"] == "# Application brief"
    assert payload["sections"]["company_fit_summary"] == "Strong fit"
    assert payload["sections"]["key_requirements"] == ["Requirement 1"]


def test_application_brief_endpoint_uses_fallback_generation_without_openai():
    app = create_app(settings=Settings(openai_api_key=None))
    client = TestClient(app)

    response = client.post(
        "/api/application-brief",
        headers={"X-Request-ID": "journey-fallback"},
        json={
            "company_description": "We build AI tools for industrial companies across Europe and support trusted deployment.",
            "match_result": {
                "grant_id": "TOPIC-1",
                "title": "AI Grant",
                "status": "Open",
                "portal_url": "https://example.com/TOPIC-1",
                "fit_score": 56,
                "why_match": "Matched on keywords: ai, safety.",
                "application_angle": "Lead with deployment outcomes",
                "keywords": ["ai", "safety"],
            },
            "grant_detail": {
                "grant_id": "TOPIC-1",
                "full_description": "",
                "eligibility_criteria": ["EU legal entity"],
                "submission_deadlines": [{"label": "Main deadline", "value": "2026-08-01"}],
                "expected_outcomes": [],
                "documents": [],
                "partner_search_available": False,
                "source": "match_result_fallback",
                "fallback_used": True,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "journey-fallback"
    assert "AI Grant application brief" in payload["markdown"]
    assert "Final week before 2026-08-01" in payload["markdown"]
    assert "Research institution with EU delivery experience" in payload["sections"]["suggested_consortium_partners"]


def test_application_brief_endpoint_reports_service_failure():
    class FailingBriefService:
        def generate(self, **_kwargs):
            raise RuntimeError("brief generation failed")

    app = create_app()
    app.state.application_brief_service = FailingBriefService()
    client = TestClient(app)

    response = client.post(
        "/api/application-brief",
        headers={"X-Request-ID": "journey-123"},
        json={
            "company_description": "We build AI tools for industrial companies.",
            "match_result": {
                "grant_id": "TOPIC-1",
                "title": "AI Grant",
                "status": "Open",
                "portal_url": "https://example.com/TOPIC-1",
                "fit_score": 90,
                "why_match": "Strong fit",
                "application_angle": "Lead with deployment outcomes",
                "keywords": ["ai"],
            },
            "grant_detail": {
                "grant_id": "TOPIC-1",
                "full_description": "Long description",
                "eligibility_criteria": ["EU legal entity"],
                "submission_deadlines": [{"label": "Main deadline", "value": "2026-08-01"}],
                "expected_outcomes": ["Outcome 1"],
                "documents": [],
                "partner_search_available": True,
                "source": "browser_topic_detail",
                "fallback_used": False,
            },
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"]["message"] == "brief generation failed"
    assert response.json()["detail"]["request_id"] == "journey-123"


def test_application_brief_endpoint_binds_request_context_and_captures_failure(monkeypatch):
    class FailingBriefService:
        def generate(self, **_kwargs):
            raise RuntimeError("brief generation failed")

    bound = []
    captured = []
    monkeypatch.setattr("backend.app.bind_request_context", lambda **kwargs: bound.append(kwargs))
    monkeypatch.setattr(
        "backend.app.capture_backend_exception",
        lambda exc, **kwargs: captured.append((str(exc), kwargs)),
    )

    app = create_app()
    app.state.application_brief_service = FailingBriefService()
    client = TestClient(app)

    response = client.post(
        "/api/application-brief",
        headers={"X-Request-ID": "journey-456"},
        json={
            "company_description": "We build AI tools for industrial companies.",
            "match_result": {
                "grant_id": "TOPIC-1",
                "title": "AI Grant",
                "status": "Open",
                "portal_url": "https://example.com/TOPIC-1",
                "fit_score": 90,
                "why_match": "Strong fit",
                "application_angle": "Lead with deployment outcomes",
                "keywords": ["ai"],
            },
            "grant_detail": {
                "grant_id": "TOPIC-1",
                "full_description": "Long description",
                "eligibility_criteria": ["EU legal entity"],
                "submission_deadlines": [{"label": "Main deadline", "value": "2026-08-01"}],
                "expected_outcomes": ["Outcome 1"],
                "documents": [],
                "partner_search_available": True,
                "source": "browser_topic_detail",
                "fallback_used": False,
            },
        },
    )

    assert response.status_code == 502
    assert bound == [{
        "operation": "application_brief",
        "request_id": "journey-456",
        "model": app.state.settings.openai_match_model if app.state.settings.openai_api_key else None,
    }]
    assert captured == [(
        "brief generation failed",
        {
            "component": "application_brief",
            "operation": "generate_application_brief",
            "model": app.state.settings.openai_match_model,
            "fallback_used": False,
            "request_id": "journey-456",
            "context": {"grant_id": "TOPIC-1"},
        },
    )]


def test_grant_detail_endpoint_returns_normalized_payload():
    class FakeDetailService:
        def get(self, topic_id: str) -> GrantDetailResponse:
            assert topic_id == "TOPIC-1"
            return GrantDetailResponse(
                grant_id="TOPIC-1",
                full_description="Detailed description",
                eligibility_criteria=["EU legal entity"],
                submission_deadlines=[{"label": "Main deadline", "value": "2026-08-01"}],
                expected_outcomes=["Outcome A"],
                documents=[{"title": "Guide", "url": "https://example.com/guide.pdf"}],
                partner_search_available=True,
                source="topic_detail_json",
                fallback_used=False,
            )

    app = create_app()
    app.state.grant_detail_service = FakeDetailService()
    client = TestClient(app)

    response = client.get("/api/grants/TOPIC-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["grant_id"] == "TOPIC-1"
    assert payload["full_description"] == "Detailed description"
    assert payload["eligibility_criteria"] == ["EU legal entity"]


def test_grant_detail_endpoint_surfaces_missing_topic():
    class MissingDetailService:
        def get(self, topic_id: str):
            raise LookupError(f"no grant detail found for {topic_id}")

    app = create_app()
    app.state.grant_detail_service = MissingDetailService()
    client = TestClient(app)

    response = client.get("/api/grants/TOPIC-404")

    assert response.status_code == 404
    assert response.json()["detail"] == "no grant detail found for TOPIC-404"


def test_grant_detail_endpoint_falls_back_to_indexed_grant_when_upstream_missing():
    class MissingDetailService:
        def get(self, topic_id: str):
            raise LookupError(f"no grant detail found for {topic_id}")

    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self):
            return IndexStatus(
                phase="ready",
                message="Ready",
                indexed_grants=1,
                scanned_prefixes=1,
                total_prefixes=1,
                failed_prefixes=0,
                truncated_prefixes=0,
                embeddings_ready=False,
                degraded=False,
                coverage_complete=True,
                matching_available=True,
                degradation_reasons=[],
            )

        def get_grants(self):
            from backend.models import GrantRecord

            return [
                GrantRecord(
                    id="TOPIC-1",
                    title="AI Grant",
                    status="Open",
                    portal_url="https://example.com/TOPIC-1",
                    deadline="2026-08-01",
                    budget_display="EUR 5M",
                    description="Indexed fallback description",
                )
            ]

    app = create_app(app_state=FakeState())
    app.state.grant_detail_service = MissingDetailService()
    client = TestClient(app)

    response = client.get("/api/grants/TOPIC-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["grant_id"] == "TOPIC-1"
    assert payload["full_description"] == "Indexed fallback description"
    assert payload["fallback_used"] is True
