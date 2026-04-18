from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import sentry_sdk

from .config import Settings, load_settings
from .embeddings import EmbeddingService, embedding_shortlist, lexical_shortlist
from .matcher import MatchService, OpenAIScorer
from .models import HealthResponse, IndexStatus, MatchRequest, MatchResponse
from .state import AppState

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_SENTRY_INITIALIZED = False


def initialize_sentry(settings: Settings) -> None:
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED or not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=True,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    _SENTRY_INITIALIZED = True


def build_match_service(settings: Settings, app_state: AppState) -> MatchService:
    embedding_service = None
    scorer = None

    if settings.openai_api_key:
        embedding_service = EmbeddingService(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        scorer = OpenAIScorer(
            model=settings.openai_match_model,
            api_key=settings.openai_api_key,
        )

    def shortlist(company_description, grants, limit):
        if embedding_service is not None:
            grant_embeddings = app_state.get_grant_embeddings()
            if grant_embeddings:
                try:
                    return embedding_shortlist(
                        company_description,
                        grants,
                        grant_embeddings=grant_embeddings,
                        embedding_service=embedding_service,
                        limit=limit,
                    )
                except Exception:
                    pass
        return lexical_shortlist(company_description, grants, limit=limit)

    return MatchService(
        shortlister=shortlist,
        scorer=scorer.score if scorer is not None else None,
    )


def create_app(
    *,
    settings: Settings | None = None,
    app_state: AppState | None = None,
    match_service: object | None = None,
) -> FastAPI:
    active_settings = settings or load_settings()
    initialize_sentry(active_settings)

    if app_state is None:
        index_embedding_service = None
        if active_settings.openai_api_key:
            index_embedding_service = EmbeddingService(
                model=active_settings.openai_embedding_model,
                api_key=active_settings.openai_api_key,
            )
        app_state = AppState(
            settings=active_settings,
            embedding_service=index_embedding_service,
        )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        app_state.ensure_indexing_started()
        yield

    app = FastAPI(title="EU Grant Matcher", lifespan=lifespan)
    app.state.settings = active_settings
    app.state.app_state = app_state
    app.state.match_service = match_service or build_match_service(active_settings, app_state)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    def styles() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "styles.css")

    @app.get("/app.js", include_in_schema=False)
    def javascript() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "app.js")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/index/status", response_model=IndexStatus)
    def index_status() -> IndexStatus:
        app.state.app_state.ensure_indexing_started()
        return app.state.app_state.get_status()

    @app.post("/api/match", response_model=MatchResponse)
    def match_company(payload: MatchRequest) -> MatchResponse:
        app.state.app_state.ensure_indexing_started()
        status = app.state.app_state.get_status()
        if status.phase != "ready":
            raise HTTPException(status_code=503, detail={"phase": status.phase, "message": status.message})

        grants = app.state.app_state.get_grants()
        return app.state.match_service.match(
            payload.company_description,
            grants,
            now=datetime.now(timezone.utc),
            limit=app.state.settings.shortlist_limit,
        )

    @app.get("/sentry-debug")
    def sentry_debug() -> None:
        _ = 1 / 0

    return app


app = create_app()
