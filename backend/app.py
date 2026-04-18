from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import time

import sentry_sdk
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .application_brief import ApplicationBriefService
from .config import Settings, load_settings
from .embeddings import EmbeddingService, embedding_shortlist, lexical_shortlist
from .grant_detail import GrantDetailService, build_grant_record_fallback
from .matcher import MatchService, OpenAIScorer
from .models import (
    ApplicationBriefRequest,
    ApplicationBriefResponse,
    GrantDetailResponse,
    HealthResponse,
    IndexStatus,
    MatchRequest,
    MatchResponse,
    ProfileResolveRequest,
    ProfileResolveResponse,
    ProfileFromWebsiteRequest,
    ProfileFromWebsiteResponse,
    ReadinessResponse,
)
from .observability import bind_request_context, capture_backend_exception, initialize_sentry
from .openai_client import build_openai_client
from .profile_resolver import DemoProfileResolver, OpenAICompanyProfileExpander
from .request_ids import resolve_request_id
from .website_profile import OpenAIWebsiteProfileGenerator, WebsiteProfileService, fetch_website_html
from .state import AppState

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='18' fill='#006d5b'/>"
    "<path d='M18 24h28v6H18zm0 10h20v6H18zm0 10h28v6H18z' fill='#fff7ec'/>"
    "</svg>"
)
MATCH_NOT_READY_ERROR_CODE = "INDEX_NOT_READY"


def is_match_ready(status: IndexStatus) -> bool:
    return status.phase in {"ready", "ready_degraded"} and status.matching_available


def build_match_unavailable_error(status: IndexStatus, request_id: str | None = None) -> dict:
    message = status.message or "Index is not ready for matching."
    payload = {
        "code": MATCH_NOT_READY_ERROR_CODE,
        "message": message,
        "status": status.model_dump(),
    }
    if request_id is not None:
        payload["request_id"] = request_id
    return payload


def build_application_brief_error(message: str, request_id: str | None = None) -> dict:
    payload = {"message": message}
    if request_id is not None:
        payload["request_id"] = request_id
    return payload


def build_match_service(settings: Settings, app_state: AppState) -> MatchService:
    embedding_service = None
    scorer = None
    openai_client = build_openai_client(settings)

    if settings.openai_api_key:
        embedding_service = EmbeddingService(
            model=settings.openai_embedding_model,
            client=openai_client,
        )
        scorer = OpenAIScorer(
            model=settings.openai_match_model,
            client=openai_client,
            reasoning_effort=settings.openai_match_reasoning_effort,
        )

    def shortlist(company_description, grants, limit):
        grant_embeddings = app_state.get_grant_embeddings() if embedding_service is not None else {}
        sentry_sdk.set_measurement("grant_embeddings_available", 1.0 if grant_embeddings else 0.0)
        if embedding_service is not None:
            if grant_embeddings:
                try:
                    shortlisted = embedding_shortlist(
                        company_description,
                        grants,
                        grant_embeddings=grant_embeddings,
                        embedding_service=embedding_service,
                        limit=limit,
                    )
                    sentry_sdk.set_measurement("embedding_shortlist_used", 1.0)
                    sentry_sdk.set_measurement("embedding_shortlist_fallback", 0.0)
                    return shortlisted
                except Exception as exc:
                    sentry_sdk.set_measurement("embedding_shortlist_used", 0.0)
                    sentry_sdk.set_measurement("embedding_shortlist_fallback", 1.0)
                    capture_backend_exception(
                        exc,
                        component="matcher",
                        operation="embedding_shortlist",
                        model=embedding_service.model,
                        fallback_used=True,
                        context={
                            "candidate_pool": len(grants),
                        },
                    )
        sentry_sdk.set_measurement("embedding_shortlist_used", 0.0)
        sentry_sdk.set_measurement("embedding_shortlist_fallback", 1.0)
        return lexical_shortlist(company_description, grants, limit=limit)

    return MatchService(
        shortlister=shortlist,
        scorer=scorer.score if scorer is not None else None,
        on_scorer_failure=lambda exc, *, context: capture_backend_exception(
            exc,
            component="matcher",
            operation="score_candidates",
            model=settings.openai_match_model,
            fallback_used=True,
            context=context,
        ),
    )


def create_app(
    *,
    settings: Settings | None = None,
    app_state: AppState | None = None,
    match_service: object | None = None,
    profile_resolver: object | None = None,
) -> FastAPI:
    active_settings = settings or load_settings()
    initialize_sentry(active_settings)

    if app_state is None:
        openai_client = build_openai_client(active_settings)
        index_embedding_service = None
        if active_settings.openai_api_key:
            index_embedding_service = EmbeddingService(
                model=active_settings.openai_embedding_model,
                client=openai_client,
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
    app.state.grant_detail_service = GrantDetailService(timeout_seconds=active_settings.ec_timeout_seconds)
    app.state.application_brief_service = ApplicationBriefService(
        client=build_openai_client(active_settings),
        model=active_settings.openai_match_model,
        reasoning_effort=active_settings.openai_match_reasoning_effort,
    )
    app.state.profile_resolver = profile_resolver or DemoProfileResolver(
        expander=OpenAICompanyProfileExpander(
            api_key=active_settings.openai_api_key,
            model=active_settings.openai_profile_expansion_model,
            client=build_openai_client(active_settings),
            reasoning_effort=active_settings.openai_profile_reasoning_effort,
        )
        if active_settings.openai_api_key
        else None,
        on_expander_failure=lambda exc, *, context: capture_backend_exception(
            exc,
            component="profile_resolver",
            operation="expand_company_profile",
            model=active_settings.openai_profile_expansion_model,
            fallback_used=True,
            context=context,
            ),
        )

    website_profile_generator = (
        OpenAIWebsiteProfileGenerator(
            api_key=active_settings.openai_api_key,
            model=active_settings.openai_profile_expansion_model,
            client=build_openai_client(active_settings),
            reasoning_effort=active_settings.openai_profile_reasoning_effort,
        )
        if active_settings.openai_api_key
        else None
    )
    if website_profile_generator is not None:
        app.state.website_profile_service = WebsiteProfileService(
            fetch_html=fetch_website_html,
            generate_profile=website_profile_generator.generate,
        )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/styles.css", include_in_schema=False)
    def styles() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "styles.css")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> HTMLResponse:
        return HTMLResponse(FAVICON_SVG, media_type="image/svg+xml")

    @app.get("/app.js", include_in_schema=False)
    def javascript() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "app.js")

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        status = app.state.app_state.get_status()
        return HealthResponse(
            status="ok",
            readiness_phase=status.phase,
            matching_available=status.matching_available,
            degraded=status.degraded,
        )

    @app.get("/api/ready", response_model=ReadinessResponse)
    def readiness() -> ReadinessResponse | JSONResponse:
        app.state.app_state.ensure_indexing_started()
        status = app.state.app_state.get_status()
        readiness = ReadinessResponse(
            status="ready" if status.matching_available else "not_ready",
            phase=status.phase,
            message=status.message,
            degraded=status.degraded,
            degradation_reasons=status.degradation_reasons,
            snapshot_loaded=status.snapshot_loaded,
            snapshot_source=status.snapshot_source,
            refresh_in_progress=status.refresh_in_progress,
        )
        if status.matching_available:
            return readiness
        return JSONResponse(status_code=503, content=readiness.model_dump())

    @app.get("/api/index/status", response_model=IndexStatus)
    def index_status() -> IndexStatus:
        app.state.app_state.ensure_indexing_started()
        status = app.state.app_state.get_status()
        if hasattr(app.state.app_state, "get_index_summary"):
            return status.model_copy(update={"summary": app.state.app_state.get_index_summary()})
        return status

    @app.get("/api/grants/{topic_id}", response_model=GrantDetailResponse)
    def grant_detail(topic_id: str) -> GrantDetailResponse:
        try:
            return app.state.grant_detail_service.get(topic_id)
        except LookupError as exc:
            grants = app.state.app_state.get_grants() if hasattr(app.state.app_state, "get_grants") else []
            fallback = next((grant for grant in grants if getattr(grant, "id", None) == topic_id), None)
            if fallback is not None:
                return build_grant_record_fallback(fallback)
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/profile/resolve", response_model=ProfileResolveResponse)
    def profile_resolve(
        payload: ProfileResolveRequest,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> ProfileResolveResponse:
        request_id = resolve_request_id(x_request_id)
        bind_request_context(
            operation="profile_resolve",
            request_id=request_id,
            model=active_settings.openai_profile_expansion_model if active_settings.openai_api_key else None,
        )
        resolution = app.state.profile_resolver.resolve(payload.query)
        return ProfileResolveResponse(
            resolved=resolution.resolved,
            profile=resolution.profile,
            display_name=resolution.display_name,
            source=resolution.source,
            message=resolution.message,
        )

    @app.post("/api/profile/from-website", response_model=ProfileFromWebsiteResponse)
    def profile_from_website(
        payload: ProfileFromWebsiteRequest,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> ProfileFromWebsiteResponse:
        request_id = resolve_request_id(x_request_id)
        bind_request_context(
            operation="website_profile_resolve",
            request_id=request_id,
            model=active_settings.openai_profile_expansion_model if active_settings.openai_api_key else None,
        )
        website_profile_service = getattr(app.state, "website_profile_service", None)
        if website_profile_service is None:
            raise HTTPException(
                status_code=503,
                detail={"message": "website profile service unavailable", "request_id": request_id},
            )
        try:
            resolution = website_profile_service.resolve(payload.url)
            return ProfileFromWebsiteResponse(
                resolved=resolution.resolved,
                profile=resolution.profile,
                display_name=resolution.display_name,
                source=resolution.source,
                normalized_url=resolution.normalized_url,
                message=resolution.message,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": str(exc), "request_id": request_id},
            ) from exc
        except Exception as exc:
            capture_backend_exception(
                exc,
                component="website_profile",
                operation="generate_website_profile",
                model=active_settings.openai_profile_expansion_model,
                request_id=request_id,
                fallback_used=False,
                context={"url": payload.url},
            )
            raise HTTPException(
                status_code=502,
                detail={"message": str(exc), "request_id": request_id},
            ) from exc

    @app.post("/api/match", response_model=MatchResponse)
    def match_company(
        payload: MatchRequest,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> MatchResponse:
        app.state.app_state.ensure_indexing_started()
        request_id = resolve_request_id(x_request_id)
        bind_request_context(
            operation="match",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        status = app.state.app_state.get_status()
        if not is_match_ready(status):
            raise HTTPException(
                status_code=503,
                detail=build_match_unavailable_error(status, request_id=request_id),
            )

        grants = app.state.app_state.get_grants()
        match_response = app.state.match_service.match(
            payload.company_description,
            grants,
            now=datetime.now(timezone.utc),
            limit=app.state.settings.shortlist_limit,
            base_degradation_reasons=status.degradation_reasons,
        )
        sentry_sdk.set_measurement("grant_embeddings_available", 1.0 if status.embeddings_ready else 0.0)
        return match_response.model_copy(update={"request_id": request_id})

    @app.post("/api/application-brief", response_model=ApplicationBriefResponse)
    def application_brief(
        payload: ApplicationBriefRequest,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> ApplicationBriefResponse:
        started_at = time.perf_counter()
        request_id = resolve_request_id(x_request_id)
        bind_request_context(
            operation="application_brief",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        brief_service = getattr(app.state, "application_brief_service", None)
        if brief_service is None:
            raise HTTPException(
                status_code=503,
                detail=build_application_brief_error("application brief service unavailable", request_id),
            )
        try:
            response = brief_service.generate(
                company_description=payload.company_description,
                match_result=payload.match_result.model_dump(),
                grant_detail=payload.grant_detail.model_dump(),
            )
            sentry_sdk.set_measurement("application_brief_failed", 0.0)
            return response.model_copy(update={"request_id": request_id})
        except Exception as exc:
            sentry_sdk.set_measurement("application_brief_failed", 1.0)
            capture_backend_exception(
                exc,
                component="application_brief",
                operation="generate_application_brief",
                model=active_settings.openai_match_model,
                request_id=request_id,
                fallback_used=False,
                context={"grant_id": payload.match_result.grant_id},
            )
            raise HTTPException(
                status_code=502,
                detail=build_application_brief_error(str(exc), request_id),
            ) from exc
        finally:
            sentry_sdk.set_measurement(
                "application_brief_route_latency_ms",
                round((time.perf_counter() - started_at) * 1000, 3),
            )

    @app.get("/sentry-debug")
    def sentry_debug() -> None:
        _ = 1 / 0

    return app


app = create_app()
