import json
import shutil
import subprocess
from pathlib import Path

import pytest
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


def test_shim_command_executes_help():
    script = Path("scripts/eufundingme")
    assert script.exists()

    completed = subprocess.run([str(script), "--help"], check=False, capture_output=True, text=True)
    assert completed.returncode == 0
    assert "match" in completed.stdout


def test_installable_eufundingme_entrypoint():
    eufundingme_bin = shutil.which("eufundingme")
    if eufundingme_bin is None:
        pytest.skip("eufundingme command not installed in this environment")

    completed = subprocess.run(
        [eufundingme_bin, "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "match" in completed.stdout
