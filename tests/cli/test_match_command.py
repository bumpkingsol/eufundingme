import json

from tests.cli._helpers import run_cli


def test_match_command_returns_json_results():
    code, stdout, _ = run_cli(
        ["match", "--description", "We build AI safety tools across Europe.", "--json"]
    )

    assert code == 0
    payload = json.loads(stdout)
    assert payload["indexed_grants"] >= 0
    assert "results" in payload


def test_match_command_outputs_stderr_on_missing_args():
    code, _, stderr = run_cli(["match"])

    assert code != 0
    assert "description" in stderr.lower()
