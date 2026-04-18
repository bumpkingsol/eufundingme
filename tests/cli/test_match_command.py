import json

from tests.cli._helpers import run_cli
from backend.models import MatchResponse
from backend.cli_services import run_match_query


def test_match_command_returns_json_results():
    code, stdout, _ = run_cli(
        ["match", "--description", "We build AI safety tools across Europe.", "--json"]
    )

    assert code == 0
    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["indexed_grants"] >= 0
    assert "results" in payload


def test_match_command_outputs_stderr_on_missing_args():
    code, _, stderr = run_cli(["match"])

    assert code != 0
    assert "description" in stderr.lower()


def test_match_query_blocks_until_ready():
    class FakeMatchService:
        def match(self, company_description, grants, now=None, limit: int = 10):
            return MatchResponse(indexed_grants=0, results=[])

    class FakeState:
        def __init__(self) -> None:
            self.calls = 0

        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self):
            self.calls += 1
            from backend.models import IndexStatus

            if self.calls < 2:
                return IndexStatus(phase="building", message="Indexing live grants", indexed_grants=0)
            return IndexStatus(
                phase="ready",
                message="Index ready",
                indexed_grants=0,
                coverage_complete=True,
                matching_available=True,
            )

        def get_grants(self):
            return []

    class FakeAppState:
        def __init__(self, state) -> None:
            self.app_state = state
            self.settings = type("Settings", (), {"shortlist_limit": 10})()
            self.match_service = FakeMatchService()

    fake_app = type("App", (), {"state": FakeAppState(FakeState())})()

    import backend.cli_services

    original_create_app = backend.cli_services.create_app
    backend.cli_services.create_app = lambda: fake_app
    try:
        code, payload = run_match_query(
            "We build AI safety tools across Europe.",
            wait_timeout_seconds=2.0,
            poll_interval_seconds=0.0,
        )
    finally:
        backend.cli_services.create_app = original_create_app

    assert code == 0
    assert payload["ok"] is True


def test_match_query_times_out_when_not_ready():
    class FakeState:
        def __init__(self) -> None:
            self.calls = 0

        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self):
            self.calls += 1
            from backend.models import IndexStatus

            return IndexStatus(phase="building", message="Indexing live grants", indexed_grants=0)

    class FakeAppState:
        def __init__(self, state) -> None:
            self.app_state = state
            self.settings = type("Settings", (), {"shortlist_limit": 10})()

    fake_app = type("App", (), {"state": FakeAppState(FakeState())})()

    import backend.cli_services

    original_create_app = backend.cli_services.create_app
    backend.cli_services.create_app = lambda: fake_app
    try:
        code, payload = run_match_query(
            "We build AI safety tools across Europe.",
            wait_timeout_seconds=0.01,
            poll_interval_seconds=0.0,
        )
    finally:
        backend.cli_services.create_app = original_create_app

    assert code == 3
    assert payload["ok"] is False
    assert payload["error"]["code"] == "MATCH_TIMEOUT"


def test_match_query_fails_when_matching_unavailable():
    class FakeState:
        def ensure_indexing_started(self) -> None:
            return None

        def get_status(self):
            from backend.models import IndexStatus

            return IndexStatus(
                phase="ready",
                message="Index ready but degraded",
                indexed_grants=0,
                matching_available=False,
                degraded=True,
                degradation_reasons=["partial_coverage"],
            )

        def get_grants(self):
            return []

    class FakeAppState:
        def __init__(self, state) -> None:
            self.app_state = state
            self.settings = type("Settings", (), {"shortlist_limit": 10})()

    fake_app = type("App", (), {"state": FakeAppState(FakeState())})()

    import backend.cli_services

    original_create_app = backend.cli_services.create_app
    backend.cli_services.create_app = lambda: fake_app
    try:
        code, payload = run_match_query(
            "We build AI safety tools across Europe.",
            wait_timeout_seconds=0.01,
            poll_interval_seconds=0.0,
        )
    finally:
        backend.cli_services.create_app = original_create_app

    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INDEX_NOT_READY"
