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
    assert 'minlength="20"' in response.text
    assert "status-failures" in response.text
    assert "status-coverage" in response.text


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
            )

        def get_grants(self) -> list[object]:
            return []

    app = create_app(app_state=FakeState())
    client = TestClient(app)

    response = client.get("/api/index/status")

    assert response.status_code == 200
    assert response.json()["phase"] == "building"
    assert app.state.app_state.started is True


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


def test_sentry_debug_route_exists():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/sentry-debug")

    assert response.status_code == 500
