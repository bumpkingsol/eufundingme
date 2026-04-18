from backend.cli import build_parser


def test_cli_parser_has_required_subcommands():
    parser = build_parser()
    parsed = parser.parse_args(["match", "--description", "Demo startup with AI safety"])
    assert parsed.command == "match"
    assert parsed.wait_timeout_seconds is None
    assert parsed.poll_interval_seconds == 0.5
    assert parsed.json is False
    assert parsed.text is False


def test_cli_parser_includes_health():
    parser = build_parser()
    parsed = parser.parse_args(["health"])
    assert parsed.command == "health"


def test_cli_parser_defaults_to_json_mode():
    parser = build_parser()
    parsed = parser.parse_args(["status"])
    assert parsed.command == "status"
    assert parsed.json is False
    assert parsed.text is False
