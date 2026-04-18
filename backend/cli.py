from __future__ import annotations

import argparse
import json
import sys

from .cli_services import (
    CLI_EXIT_RUNTIME,
    CLI_EXIT_SUCCESS,
    run_health_query,
    run_index_query,
    run_match_query,
    run_profile_query,
    run_status_query,
)


CLI_VERSION = "1.0.0"


def _add_output_flags(parser: argparse.ArgumentParser) -> None:
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output (default).",
    )
    output.add_argument(
        "--text",
        action="store_true",
        help="Render human-readable plain-text output.",
    )


def _render_payload(payload: dict, *, json_enabled: bool = True) -> tuple[str, str]:
    if json_enabled:
        return json.dumps(payload), ""
    if not payload:
        return "", ""
    lines = []
    for key, value in payload.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines), ""


def build_match_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme match")
    parser.add_argument(
        "--description",
        required=True,
        help="Company description used to match relevant grants.",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=None,
        help="Maximum seconds to wait for the index to become ready.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.5,
        help="Seconds to wait between readiness checks.",
    )
    parser.add_argument(
        "--request-id",
        help="Optional request/correlation id to include in machine output.",
    )
    _add_output_flags(parser)
    return parser


def build_index_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme index")
    _add_output_flags(parser)
    return parser


def build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme status")
    _add_output_flags(parser)
    return parser


def build_profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme profile")
    parser.add_argument(
        "--query",
        required=True,
        help="Company name or short profile query.",
    )
    _add_output_flags(parser)
    return parser


def build_health_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme health")
    _add_output_flags(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme")
    parser.add_argument(
        "--version",
        action="version",
        version=f"eufundingme {CLI_VERSION}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    match_parser = subparsers.add_parser("match", help="Match grants for a company description")
    match_parser.add_argument(
        "--description",
        required=True,
        help="Company description used to match relevant grants.",
    )
    match_parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=None,
        help="Maximum seconds to wait for the index to become ready.",
    )
    match_parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.5,
        help="Seconds to wait between readiness checks.",
    )
    match_parser.add_argument(
        "--request-id",
        help="Optional request/correlation id to include in machine output.",
    )
    _add_output_flags(match_parser)

    index_parser = subparsers.add_parser("index", help="Start or inspect indexing state")
    _add_output_flags(index_parser)

    status_parser = subparsers.add_parser("status", help="Read current indexing status")
    _add_output_flags(status_parser)

    profile_parser = subparsers.add_parser("profile", help="Resolve a company name into a matching profile")
    profile_parser.add_argument("--query", required=True, help="Company name or short profile query.")
    _add_output_flags(profile_parser)

    health_parser = subparsers.add_parser("health", help="Check CLI availability")
    _add_output_flags(health_parser)

    return parser


def run_match(argv: list[str]) -> tuple[int, str, str]:
    parser = build_match_parser()
    args = parser.parse_args(argv)
    use_json = not args.text
    exit_code, payload = run_match_query(
        args.description,
        wait_timeout_seconds=args.wait_timeout_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        request_id=args.request_id,
    )
    payload = payload | {"ok": exit_code == CLI_EXIT_SUCCESS}
    return exit_code, *_render_payload(payload, json_enabled=use_json)


def run_index(argv: list[str]) -> tuple[int, str, str]:
    parser = build_index_parser()
    args = parser.parse_args(argv)
    use_json = not args.text
    return 0, *_render_payload(run_index_query(), json_enabled=use_json)


def run_status(argv: list[str]) -> tuple[int, str, str]:
    parser = build_status_parser()
    args = parser.parse_args(argv)
    use_json = not args.text
    return 0, *_render_payload(run_status_query(), json_enabled=use_json)


def run_profile(argv: list[str]) -> tuple[int, str, str]:
    parser = build_profile_parser()
    args = parser.parse_args(argv)
    use_json = not args.text
    return 0, *_render_payload(run_profile_query(args.query), json_enabled=use_json)


def run_health(argv: list[str]) -> tuple[int, str, str]:
    parser = build_health_parser()
    args = parser.parse_args(argv)
    use_json = not args.text
    payload = {"ok": True, **run_health_query()}
    return 0, *_render_payload(payload, json_enabled=use_json)


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return CLI_EXIT_RUNTIME

    if args.command == "match":
        exit_code, stdout, stderr = run_match([
            "--description", args.description,
            *(["--text"] if args.text else []),
            *(["--json"] if args.json else []),
            *(["--wait-timeout-seconds", str(args.wait_timeout_seconds)] if args.wait_timeout_seconds is not None else []),
            *(["--poll-interval-seconds", str(args.poll_interval_seconds)] if args.poll_interval_seconds is not None else []),
            *(["--request-id", args.request_id] if args.request_id else []),
        ])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "index":
        exit_code, stdout, stderr = run_index(["--text" if args.text else "--json"])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "status":
        exit_code, stdout, stderr = run_status(["--text" if args.text else "--json"])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "profile":
        exit_code, stdout, stderr = run_profile([
            "--query", args.query,
            *(["--text"] if args.text else []),
            *(["--json"] if args.json else []),
        ])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "health":
        exit_code, stdout, stderr = run_health(["--text" if args.text else "--json"])
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    print("Command not implemented", file=sys.stderr)
    return CLI_EXIT_RUNTIME


if __name__ == "__main__":
    raise SystemExit(main())
