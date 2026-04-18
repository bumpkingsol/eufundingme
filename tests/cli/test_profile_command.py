import json

from tests.cli._helpers import run_cli


def test_profile_command_resolves_known_demo_name():
    code, stdout, _ = run_cli(["profile", "--query", "OpenAI", "--json"])

    assert code == 0
    payload = json.loads(stdout)
    assert payload["resolved"] is True
    assert payload["source"] in {"demo_profile", "llm_expansion"}
