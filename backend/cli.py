from __future__ import annotations

import argparse
import json
import sys

from .cli_services import run_index_query, run_match_query, run_profile_query, run_status_query


def build_match_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme match")
    parser.add_argument(
        "--description",
        required=True,
        help="Company description used to match relevant grants.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )
    return parser


def build_index_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme index")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )
    return parser


def build_status_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme status")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )
    return parser


def build_profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme profile")
    parser.add_argument(
        "--query",
        required=True,
        help="Company name or short profile query.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme")
    subparsers = parser.add_subparsers(dest="command", required=True)

    match_parser = subparsers.add_parser("match", help="Match grants for a company description")
    match_parser.add_argument(
        "--description",
        help="Company description used to match relevant grants.",
    )
    match_parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )

    index_parser = subparsers.add_parser("index", help="Start/inspect indexing state")
    index_parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )

    status_parser = subparsers.add_parser("status", help="Read indexing status")
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )

    profile_parser = subparsers.add_parser("profile", help="Resolve a company name into a matching profile")
    profile_parser.add_argument("--query", required=True, help="Company name or short profile query.")
    profile_parser.add_argument(
        "--json",
        action="store_true",
        help="Render machine-friendly JSON output.",
    )

    return parser


def _render_json(payload: dict, *, json_enabled: bool = True) -> tuple[str, str]:
    if json_enabled:
        return json.dumps(payload), ""
    lines = []
    for key, value in payload.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines), ""


def run_match(argv: list[str]) -> tuple[int, str, str]:
    """Execute the match command with machine-oriented output."""

    parser = build_match_parser()
    args = parser.parse_args(argv)

    payload = run_match_query(args.description)

    return 0, *_render_json(payload)


def run_index(argv: list[str]) -> tuple[int, str, str]:
    parser = build_index_parser()
    args = parser.parse_args(argv)

    payload = run_index_query()
    return 0, *_render_json(payload, json_enabled=args.json)


def run_status(argv: list[str]) -> tuple[int, str, str]:
    parser = build_status_parser()
    args = parser.parse_args(argv)

    payload = run_status_query()
    return 0, *_render_json(payload, json_enabled=args.json)


def run_profile(argv: list[str]) -> tuple[int, str, str]:
    parser = build_profile_parser()
    args = parser.parse_args(argv)

    payload = run_profile_query(args.query)
    return 0, *_render_json(payload, json_enabled=args.json)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "match":
        match_argv = ["--json"] if args.json else []
        if args.description is not None:
            match_argv = ["--description", args.description] + match_argv

        exit_code, stdout, stderr = run_match(match_argv)
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "index":
        index_argv = ["--json"] if args.json else []
        exit_code, stdout, stderr = run_index(index_argv)
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "status":
        status_argv = ["--json"] if args.json else []
        exit_code, stdout, stderr = run_status(status_argv)
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    if args.command == "profile":
        profile_argv = ["--query", args.query]
        if args.json:
            profile_argv.append("--json")
        exit_code, stdout, stderr = run_profile(profile_argv)
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)
        return exit_code

    print("Command not implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
