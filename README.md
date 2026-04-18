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

## API

- `GET /api/health`
- `GET /api/index/status`
- `POST /api/match`
- `GET /sentry-debug`

Example match request:

```bash
curl http://127.0.0.1:8000/api/match \
  -H "Content-Type: application/json" \
  -d '{"company_description":"We build AI safety tooling for enterprise deployment across Europe."}'
```

## Notes

- The EC API ignores server-side status filters, so indexing uses call-prefix fan-out and client-side filtering.
- The app keeps the grant index in memory for speed.
- By default the crawler runs exhaustively across pages for each prefix. Set `EC_MAX_PAGES_PER_PREFIX` only if you want an explicit crawl cap; capped crawls are reported as degraded coverage.
- If `OPENAI_API_KEY` is not set, the app stays available in lexical-only mode and reports degraded matching quality.
- If embeddings or AI scoring fail at runtime, the app falls back to lexical ranking and marks the match/index state as degraded.
- If `SENTRY_DSN` is not set, the app still runs but no Sentry monitoring is emitted.
