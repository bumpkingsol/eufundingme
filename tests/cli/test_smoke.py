from tests.cli._helpers import run_cli


def test_cli_help_exists():
    code, stdout, _ = run_cli(["--help"])

    assert code == 0
    assert "match" in stdout
    assert "index" in stdout
    assert "status" in stdout
    assert "profile" in stdout


def test_cli_smoke():
    code, stdout, _ = run_cli(["--help"])

    assert code == 0
    assert stdout
