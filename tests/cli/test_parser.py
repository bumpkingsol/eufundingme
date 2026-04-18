from backend.cli import build_parser


def test_cli_parser_has_required_subcommands():
    parser = build_parser()
    parsed = parser.parse_args(["match"])
    assert parsed.command == "match"
