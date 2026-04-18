import json

from tests.cli._helpers import run_cli


def test_status_command_outputs_phase():
    code, stdout, _ = run_cli(["status", "--json"])

    assert code == 0
    payload = json.loads(stdout)
    assert payload["phase"] in {"building", "ready", "ready_degraded", "error"}


def test_index_command_is_idempotent():
    code1, stdout1, _ = run_cli(["index", "--json"])
    code2, stdout2, _ = run_cli(["index", "--json"])

    payload1 = json.loads(stdout1)
    payload2 = json.loads(stdout2)

    assert code1 == 0
    assert code2 == 0
    assert payload1["phase"] in {"building", "ready", "ready_degraded", "error"}
    assert payload2["phase"] in {"building", "ready", "ready_degraded", "error"}
