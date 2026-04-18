from __future__ import annotations

import subprocess
import sys


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "backend.cli", *argv],
        check=False,
        capture_output=True,
        text=True,
    )

    return completed.returncode, completed.stdout, completed.stderr
