import json

from tests.cli._helpers import run_cli


def test_status_schema_contract_is_stable():
    code, stdout, _ = run_cli(["status", "--json"])

    assert code == 0
    payload = json.loads(stdout)
    expected_fields = {
        "phase",
        "message",
        "indexed_grants",
        "scanned_prefixes",
        "total_prefixes",
        "failed_prefixes",
        "embeddings_ready",
        "started_at",
        "finished_at",
        "degraded",
        "degradation_reasons",
        "matching_available",
        "coverage_complete",
        "truncated_prefixes",
    }
    assert expected_fields.issubset(payload.keys())
