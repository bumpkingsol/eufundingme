from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import IndexStatus, MatchResponse, MatchResult


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "readiness_phase": "idle",
        "matching_available": False,
        "degraded": False,
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

    app = create_app(app_state=FakeState())
    client = TestClient(app)

    response = client.get("/api/index/status")

    assert response.status_code == 200
    assert response.json()["phase"] == "building"
    assert response.json()["current_prefix"] == "HORIZON-CL4-2026"
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
                snapshot_age_seconds=90,
                refresh_in_progress=True,
            )

    client = TestClient(create_app(app_state=FakeState()))

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["snapshot_loaded"] is True
    assert response.json()["refresh_in_progress"] is True


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


def test_match_endpoint_keeps_short_description_validation():
    client = TestClient(create_app())

    response = client.post("/api/match", json={"company_description": "OpenAI"})

    assert response.status_code == 422
