# CLI for Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class CLI path for automated agents (Openclaw/Hermes) while preserving the existing web flow and surfacing CLI availability in the frontend.

**Architecture:** Introduce a dedicated CLI command layer that reuses the same backend services (`AppState`, `MatchService`, `MatchResponse` types). Keep web and CLI behavior consistent by sharing service factories and status schemas. Return stable JSON for machine consumers and keep human-readable text optional.

**Tech Stack:** Python 3.12+, FastAPI internals reused by CLI, argparse or click, and existing tests plus new CLI-focused tests.

---

### Task 1: Add shared CLI entrypoint surface

**Files:**
- Create: `backend/cli.py`

- [ ] **Step 1: Write the failing test**

```python
from backend.cli import build_parser


def test_cli_parser_has_required_subcommands():
    parser = build_parser()
    parsed = parser.parse_args(["match"])
    assert parsed.command == "match"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_parser.py -q`

Expected: `ModuleNotFoundError` for `backend.cli` or parser attribute mismatch.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eufundingme")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("match")
    subparsers.add_parser("index")
    subparsers.add_parser("status")
    subparsers.add_parser("profile")
    return parser
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_parser.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli.py tests/cli/test_parser.py
git commit -m "feat(cli): add cli parser scaffold"
```

### Task 2: Implement scriptable match command

**Files:**
- Modify: `backend/cli.py`
- Create: `backend/cli_services.py`
- Create: `tests/cli/_helpers.py`
- Create: `tests/cli/test_match_command.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from tests.cli._helpers import run_cli


def test_match_command_returns_json_results():
    code, stdout, _ = run_cli(["match", "--description", "We build AI safety tools across Europe.", "--json"])
    assert code == 0
    payload = json.loads(stdout)
    assert payload["indexed_grants"] >= 0
    assert "results" in payload


def test_match_command_outputs_stderr_on_missing_args():
    code, _, stderr = run_cli(["match"])
    assert code != 0
    assert "description" in stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_match_command.py -q`

Expected: FAIL due missing CLI execution function.

- [ ] **Step 3: Write minimal implementation**

```python
def run_match(argv: list[str]) -> tuple[int, str, str]:
    # 1) ensure index is ready (blocking with timeout and status polling)
    # 2) call MatchService.match
    # 3) print structured dict: {"indexed_grants": n, "results": [...], "status": {...}}
    # 4) return (exit_code, stdout, stderr)
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_match_command.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli.py backend/cli_services.py tests/cli/test_match_command.py
git commit -m "feat(cli): implement match command with structured output"
```

### Task 3: Add CLI index and status commands

**Files:**
- Modify: `backend/cli.py`
- Create: `tests/cli/test_index_status_commands.py`

- [ ] **Step 1: Write the failing test**

```python
def test_status_command_outputs_phase():
    code, stdout, _ = run_cli(["status", "--json"])
    payload = json.loads(stdout)
    assert code == 0
    assert payload["phase"] in {"building", "ready", "error"}


def test_index_command_is_idempotent():
    code1, stdout1, _ = run_cli(["index"])
    code2, stdout2, _ = run_cli(["index"])
    payload1 = json.loads(stdout1)
    payload2 = json.loads(stdout2)
    assert code1 == 0
    assert code2 == 0
    assert payload1["phase"] in {"building", "ready", "error"}
    assert payload2["phase"] in {"building", "ready", "error"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_index_status_commands.py -q`

Expected: FAIL due missing status command.

- [ ] **Step 3: Write minimal implementation**

```python
def run_status(argv: list[str]):
    status = state.get_status()
    return 0, json.dumps({"phase": status.phase, "message": status.message}), ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_index_status_commands.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/cli.py tests/cli/test_index_status_commands.py
git commit -m "feat(cli): add status and index commands"
```

### Task 4: Add CLI profile resolution command and robust resolver loading

**Files:**
- Modify: `backend/profile_resolver.py`
- Modify: `backend/cli.py`
- Create: `tests/cli/test_profile_command.py`

- [ ] **Step 1: Write the failing test**

```python
def test_profile_command_resolves_known_demo_name():
    code, stdout, _ = run_cli(["profile", "--query", "OpenAI", "--json"])
    payload = json.loads(stdout)
    assert code == 0
    assert payload["resolved"] is True
    assert payload["source"] in {"demo_profile", "llm_expansion"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_profile_command.py -q`

Expected: FAIL due missing command and demo-profile path brittleness.

- [ ] **Step 3: Write minimal implementation**

```python
def resolve_profile_path():
    # prefer environment or package resource, then fallback to parent path
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_profile_command.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/profile_resolver.py backend/cli.py tests/cli/test_profile_command.py
git commit -m "feat(cli): add profile command and stable profile resource loading"
```

### Task 5: Synchronize status schema for UI + CLI visibility

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/state.py`
- Modify: `backend/app.py`
- Modify: `frontend/app.js`
- Create: `tests/cli/test_status_schema_contract.py`

- [ ] **Step 1: Write the failing test**

```python
def test_status_schema_contract_is_stable():
    # status should expose coverage/availability fields used by both UI and CLI
    code, stdout, _ = run_cli(["status", "--json"])
    payload = json.loads(stdout)
    assert set(payload.keys()).issuperset(
        {
            "phase",
            "message",
            "indexed_grants",
            "scanned_prefixes",
            "total_prefixes",
            "failed_prefixes",
            "embeddings_ready",
            "started_at",
            "finished_at",
            "degraded",
            "degradation_reasons",
            "matching_available",
            "coverage_complete",
            "truncated_prefixes",
        }
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_status_schema_contract.py -q`

Expected: FAIL (attributes missing in model today).

- [ ] **Step 3: Write minimal implementation**

```python
class IndexStatus(BaseModel):
    ...
    degraded: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    matching_available: bool = True
    coverage_complete: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/cli/test_status_schema_contract.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/state.py backend/app.py frontend/app.js tests/cli/test_status_schema_contract.py
git commit -m "fix: expose stable indexing status fields for UI and CLI"
```

### Task 6: Make CLI-first messaging explicit in frontend

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/app.js` (if helpful copy text/links)

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_frontend_mentions_cli():
    html = Path("frontend/index.html").read_text()
    assert "CLI" in html
    assert "python -m backend.cli" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_frontend_contract.py -q`

Expected: FAIL as text is missing.

- [ ] **Step 3: Write minimal implementation**

```html
<section class="cli-callout">
  <p class="submit-hint">Agents can use CLI mode: <code>python -m backend.cli match --description \"...\" --json</code>.</p>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_frontend_contract.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/styles.css frontend/app.js tests/test_frontend_contract.py
git commit -m "feat(ui): expose CLI usage in frontend hero area"
```

### Task 7: Align docs and run end-to-end checks

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/superpowers/plans/2026-04-18-cli-for-agents.md` (already created)

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_readme_lists_cli_usage_and_api_contract():
    text = Path("README.md").read_text()
    assert "CLI" in text
    assert "python -m backend.cli" in text
    assert "/api/profile/resolve" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_docs_contract.py -q`

Expected: FAIL due missing docs updates.

- [ ] **Step 3: Write minimal implementation**

```markdown
- Add `python -m backend.cli match --description "..." --json`
- Add `backend.cli index`, `backend.cli status`, `backend.cli profile`
- Expand `.env.example` to include all documented knobs used by both scoring and profile resolver
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_docs_contract.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs: add CLI usage and agent-oriented API contract"
```

### Task 8: CLI integration smoke and release verification

**Files:**
- Run: no code changes
- Tests: `tests/cli/*` and existing suites

- [ ] **Step 1: Write the failing test**

Add a smoke command test file:
`tests/cli/test_smoke.py`

```python
def test_cli_smoke():
    code, stdout, _ = run_cli(["--help"])
    assert code == 0
    assert stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/cli/test_smoke.py -q`

Expected: FAIL for first run.

- [ ] **Step 3: Write minimal implementation**

```python
def test_cli_help_exists():
    code, stdout, _ = run_cli(["--help"])
    assert code == 0
    assert "match" in stdout
    assert "status" in stdout
    assert "index" in stdout
    assert "profile" in stdout
```

- [ ] **Step 4: Run full verification command**

Run:
```bash
python -m pytest tests -q
python -m backend.cli --help
python -m backend.cli match --description "We build AI safety tooling across Europe." --json
```

Expected: Tests pass; CLI prints usage and returns JSON.

- [ ] **Step 5: Commit**

```bash
git add tests/cli tests/test_docs_contract.py
git commit -m "test: add CLI smoke tests and final verification"
```

Execution options (after plan review):  
1) **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks.  
2) **Inline Execution** - execute tasks in this session using executing-plans with checkpoints for review.
