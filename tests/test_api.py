from fastapi.testclient import TestClient

from backend.app import create_app
from backend.models import IndexStatus, MatchResponse, MatchResult


def test_health_endpoint_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_route_serves_frontend_shell():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Find EU funding for your company in 30 seconds." in response.text


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
                embeddings_ready=False,
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
                phase="ready",
                message="Ready",
                indexed_grants=32,
                scanned_prefixes=10,
                total_prefixes=10,
                failed_prefixes=0,
                embeddings_ready=True,
            )

        def get_grants(self) -> list[object]:
            return ["placeholder"]

    class FakeMatchService:
        def match(self, company_description: str, grants: list[object], now=None, limit: int = 10) -> MatchResponse:
            assert company_description == "We build AI safety tooling across Europe."
            assert grants == ["placeholder"]
            return MatchResponse(
                indexed_grants=32,
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


def test_sentry_debug_route_exists():
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/sentry-debug")

    assert response.status_code == 500
