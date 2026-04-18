# EU Grant Matcher

Find EU funding for your company in 30 seconds.

This open-source app works in three steps:

1. Index live EU grants from the European Commission search API
2. Shortlist the strongest candidates with embeddings or lexical fallback
3. Rank and explain the best matches with OpenAI

## Stack

- FastAPI backend
- Static HTML, CSS, and vanilla JavaScript frontend
- OpenAI for embeddings and grant scoring
- Sentry for error and performance monitoring

## Environment

Set these before running the app:

```bash
export OPENAI_API_KEY=...
export OPENAI_MATCH_MODEL=gpt-4o-2024-08-06
export OPENAI_EMBEDDING_MODEL=text-embedding-3-large
export SENTRY_DSN=...
```

Optional overrides:

```bash
export HOST=127.0.0.1
export PORT=8000
export EC_PAGE_SIZE=100
export EC_MAX_PAGES_PER_PREFIX=3
export EC_TIMEOUT_SECONDS=30
export EC_MAX_RETRIES=2
export EC_RETRY_BACKOFF_SECONDS=0.5
export SHORTLIST_LIMIT=10
export SENTRY_TRACES_SAMPLE_RATE=0.2
export INDEX_SNAPSHOT_PATH=.cache/grant-index.json
export INDEX_SNAPSHOT_MAX_AGE_HOURS=24
export INDEX_REFRESH_STALL_SECONDS=60
export DEMO_PROFILES_PATH=...
```

## Run

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt pytest
uvicorn backend.app:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Test

Use `python -m pytest` from the project root.

```bash
. .venv/bin/activate
python -m pytest tests -q
```

## CLI

Use the CLI in machine-first mode for agents (JSON output and stable errors are default):

Install once for agent automation:

```bash
pip install -e .
# or pip install .
```

```bash
# Installable command (preferred for agents)
eufundingme match --description "We build AI safety tooling for enterprise deployment across Europe."

# Fallback for local/dev environments
python -m backend.cli match --description "We build AI safety tooling for enterprise deployment across Europe."
python -m backend.cli index
python -m backend.cli status
python -m backend.cli profile --query "OpenAI"
python -m backend.cli health
```

`eufundingme match` emits:

- `--wait-timeout-seconds` (default: 60) to wait for index readiness.
- `--poll-interval-seconds` (default: 0.5) between readiness checks.

Exit codes:

- `0` success
- `2` validation/readiness blocked (`INDEX_NOT_READY`)
- `3` timeout waiting for index
- `1` runtime failure (`INTERNAL_ERROR`)

JSON envelope (error example):

```json
{
  "ok": false,
  "error": {
    "code": "INDEX_NOT_READY",
    "message": "Index is not ready for matching.",
    "status": { "...": "..." }
  },
  "request_id": "..."
}
```

You can pin trace IDs with `--request-id`:

```bash
eufundingme match --description "..." --request-id "agent-run-123"
```

## API

- `GET /api/health`
- `GET /api/ready`
- `GET /api/index/status`
- `POST /api/profile/resolve`
- `POST /api/match`
- `GET /sentry-debug`

Example match request:

```bash
curl http://127.0.0.1:8000/api/match \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: optional-trace-id" \
  -d '{"company_description":"We build AI safety tooling for enterprise deployment across Europe."}'
```

## Notes

- The EC API ignores server-side status filters, so indexing uses call-prefix fan-out and client-side filtering.
- The app keeps the grant index in memory for speed.
- The app also persists the last successful completed index to disk and warm-starts from it on the next boot when available.
- By default the crawler runs exhaustively across pages for each prefix. Set `EC_MAX_PAGES_PER_PREFIX` only if you want an explicit crawl cap; capped crawls are reported as degraded coverage.
- Warm-started runs show `ready_degraded` while a background refresh is in progress. Matching stays available from the saved snapshot, but partial in-progress crawl data is never used for results.
- `INDEX_SNAPSHOT_MAX_AGE_HOURS` marks saved data as stale for operator visibility, and `INDEX_REFRESH_STALL_SECONDS` adds a `refresh_delayed` degradation signal if live crawl progress stops updating.
- Known demo companies such as `OpenAI`, `Northvolt`, and `Doctolib` resolve from checked-in profiles and are also available as one-click presets in the UI.
- Unknown short company names use OpenAI expansion only when `OPENAI_API_KEY` is configured. Without it, the UI asks for one or two descriptive sentences instead of sending the short name into `/api/match`.
- If `OPENAI_API_KEY` is not set, the app stays available in lexical-only mode and reports degraded matching quality.
- If embeddings or AI scoring fail at runtime, the app falls back to lexical ranking and marks the match/index state as degraded.
- If `SENTRY_DSN` is not set, the app still runs but no Sentry monitoring is emitted.

## Demo Flow

1. Start the app. If a saved snapshot exists, the app becomes usable immediately in `ready_degraded` while the exhaustive live refresh continues in the background.
2. Click the `OpenAI` preset to run the scripted first search.
3. Click `Northvolt` or `Doctolib` to show a contrasting sector.
4. For a live audience test, type a company name directly.
5. If the name is known, the app expands it from the saved demo profiles. If the name is unknown and OpenAI is configured, the app expands it with AI before matching.
