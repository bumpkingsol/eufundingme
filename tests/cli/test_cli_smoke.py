import json

from tests.cli._helpers import run_cli


def test_cli_help_includes_core_commands():
    code, stdout, _ = run_cli(["--help"])

    assert code == 0
    assert "match" in stdout
    assert "index" in stdout
    assert "status" in stdout
    assert "profile" in stdout
    assert "health" in stdout


def test_health_command_returns_ok_payload():
    code, stdout, _ = run_cli(["health"])

    assert code == 0
    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["status"] == "ok"
