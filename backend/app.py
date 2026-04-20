from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import time

import sentry_sdk
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .application_brief import ApplicationBriefService
from .access_control import (
    http_exception_for_billing_error,
    require_artifact_access,
    resolve_account_context,
    resolve_billing_identity,
)
from .billing_client import (
    ArtifactAccessPayload,
    BillingForbiddenError,
    BillingServiceError,
    BillingServiceUnavailableError,
    BillingUnauthorizedError,
    build_billing_client,
)
from .config import Settings, load_settings
from .ec_client import ECSearchClient
from .embeddings import EmbeddingService, build_grant_embeddings, embedding_shortlist, lexical_shortlist
from .grant_detail import GrantDetailService, build_grant_record_fallback
from .live_grant_cache import LiveGrantCache
from .live_grants import LiveGrantService
from .match_runtime import MatchCoordinator, is_match_ready
from .matcher import MatchService, OpenAIScorer
from .models import (
    ApplicationBriefRequest,
    ApplicationBriefResponse,
    AccountDashboardResponse,
    ArtifactAccessResponse,
    CreditUnlockRequest,
    CreditUnlockResponse,
    GrantDetailResponse,
    HealthResponse,
    IndexStatus,
    GuestCheckoutRequest,
    GuestCheckoutResponse,
    MatchRequest,
    MatchResponse,
    MatchAccessState,
    ProfileResolveRequest,
    ProfileResolveResponse,
    ProfileFromWebsiteRequest,
    ProfileFromWebsiteResponse,
    ReadinessResponse,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
)
from .observability import bind_request_context, capture_backend_exception, initialize_sentry
from .openai_client import build_openai_client
from .search_artifacts import SearchArtifact, SearchArtifactStore, build_locked_result_teaser
from .profile_resolver import DemoProfileResolver, OpenAICompanyProfileExpander
from .request_ids import resolve_request_id
from .translation import GrantTranslationService, OpenAIGrantTranslator
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


def _build_search_fingerprint(company_description: str) -> str:
    normalized = " ".join(company_description.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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


def _access_state_for_response(access) -> MatchAccessState:
    status = getattr(access, "status", "")
    if getattr(access, "has_access", False):
        return MatchAccessState.UNLOCKED
    if status == "expired":
        return MatchAccessState.EXPIRED
    if status in {"pending_unlock", "pending_payment", "requires_payment"}:
        return MatchAccessState.PENDING_UNLOCK
    return MatchAccessState.PREVIEW


def _artifact_access_response(artifact_id: str, access) -> ArtifactAccessResponse:
    return ArtifactAccessResponse(
        artifact_id=artifact_id,
        has_access=getattr(access, "has_access", False),
        status=getattr(access, "status", "preview"),
        expires_at=getattr(access, "expires_at", None),
        access_state=_access_state_for_response(access),
    )


def _identity_for_request(
    account_context,
    *,
    email: str | None = None,
    fingerprint: str | None = None,
) -> tuple[str | None, str | None]:
    return resolve_billing_identity(account_context, email=email, fingerprint=fingerprint)


def build_preview_match_response(
    *,
    artifact: SearchArtifact,
    access,
    request_id: str | None,
    base_response: MatchResponse,
) -> MatchResponse:
    access_state = _access_state_for_response(access)
    has_access = access_state == MatchAccessState.UNLOCKED
    results = artifact.full_results if has_access else ([artifact.preview_result] if artifact.preview_result else [])
    locked_teasers = [] if has_access else [build_locked_result_teaser(result) for result in artifact.locked_results]
    preview_result = artifact.preview_result
    return base_response.model_copy(
        update={
            "request_id": request_id,
            "results": results,
            "preview_result": preview_result,
            "locked_result_teasers": locked_teasers,
            "locked_result_count": 0 if has_access else artifact.locked_result_count,
            "access_state": access_state,
            "artifact_id": artifact.id,
        }
    )


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
        grant_embeddings = (
            app_state.get_grant_embeddings()
            if embedding_service is not None and hasattr(app_state, "get_grant_embeddings")
            else {}
        )
        sentry_sdk.set_measurement("grant_embeddings_available", 1.0 if grant_embeddings else 0.0)
        if embedding_service is not None:
            if grants and len(grants) <= 120:
                missing_grants = [grant for grant in grants if grant.id not in grant_embeddings]
                if missing_grants:
                    try:
                        grant_embeddings = {
                            **grant_embeddings,
                            **build_grant_embeddings(
                                missing_grants,
                                embedding_service=embedding_service,
                            ),
                        }
                    except Exception as exc:
                        capture_backend_exception(
                            exc,
                            component="matcher",
                            operation="build_request_embeddings",
                            model=embedding_service.model,
                            fallback_used=True,
                            context={"candidate_pool": len(grants)},
                        )
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


def build_match_coordinator(
    *,
    app_state,
    match_service,
    translation_service,
    settings: Settings,
    live_grant_service=None,
    live_grant_cache: LiveGrantCache | None = None,
    live_retrieval_capability: bool = True,
) -> MatchCoordinator:
    return MatchCoordinator(
        app_state=app_state,
        match_service=match_service,
        translation_service=translation_service,
        settings=settings,
        live_grant_service=live_grant_service,
        live_grant_cache=live_grant_cache or LiveGrantCache(),
        live_retrieval_capability=live_retrieval_capability,
    )


def create_app(
    *,
    settings: Settings | None = None,
    app_state: AppState | None = None,
    match_service: object | None = None,
    profile_resolver: object | None = None,
    live_grant_service: object | None = None,
    translation_service: object | None = None,
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
    app.state.billing_client = build_billing_client(active_settings)
    app.state.search_artifact_store = getattr(app_state, "search_artifact_store", SearchArtifactStore())
    app.state.match_service = match_service or build_match_service(active_settings, app_state)
    openai_client = build_openai_client(active_settings)
    app.state.translation_service = translation_service or GrantTranslationService(
        translator=(
            OpenAIGrantTranslator(
                model=active_settings.openai_match_model,
                client=openai_client,
                reasoning_effort="none",
            ).translate
            if openai_client is not None
            else None
        )
    )
    if live_grant_service is not None:
        app.state.live_grant_service = live_grant_service
    elif hasattr(app_state, "client"):
        app.state.live_grant_service = LiveGrantService(client=app_state.client)
    else:
        app.state.live_grant_service = None
    app.state.live_retrieval_capability = True
    app.state.live_grant_cache = LiveGrantCache()
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
    app.state.match_coordinator = build_match_coordinator(
        app_state=app.state.app_state,
        match_service=app.state.match_service,
        translation_service=app.state.translation_service,
        settings=active_settings,
        live_grant_service=app.state.live_grant_service,
        live_grant_cache=app.state.live_grant_cache,
        live_retrieval_capability=getattr(app.state, "live_retrieval_capability", False),
    )

    def sync_match_coordinator() -> MatchCoordinator:
        coordinator = app.state.match_coordinator
        coordinator.match_service = app.state.match_service
        coordinator.translation_service = app.state.translation_service
        coordinator.live_grant_service = getattr(app.state, "live_grant_service", None)
        coordinator.live_retrieval_capability = getattr(app.state, "live_retrieval_capability", False)
        return coordinator

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
        status = sync_match_coordinator().get_status()
        return HealthResponse(
            status="ok",
            readiness_phase=status.phase,
            matching_available=status.matching_available,
            degraded=status.degraded,
        )

    @app.get("/api/ready", response_model=ReadinessResponse)
    def readiness() -> ReadinessResponse | JSONResponse:
        app.state.app_state.ensure_indexing_started()
        status = sync_match_coordinator().get_status()
        readiness = ReadinessResponse(
            status="ready" if is_match_ready(status) else "not_ready",
            phase=status.phase,
            message=status.message,
            degraded=status.degraded,
            degradation_reasons=status.degradation_reasons,
            snapshot_loaded=status.snapshot_loaded,
            snapshot_source=status.snapshot_source,
            refresh_in_progress=status.refresh_in_progress,
            live_retrieval_available=status.live_retrieval_available,
            embeddings_available=status.embeddings_available,
            ai_scoring_available=status.ai_scoring_available,
            match_path=status.match_path,
        )
        if is_match_ready(status):
            return readiness
        return JSONResponse(status_code=503, content=readiness.model_dump())

    @app.get("/api/index/status", response_model=IndexStatus)
    def index_status() -> IndexStatus:
        app.state.app_state.ensure_indexing_started()
        status = sync_match_coordinator().get_status()
        if hasattr(app.state.app_state, "get_index_summary"):
            return status.model_copy(update={"summary": app.state.app_state.get_index_summary()})
        return status

    @app.get("/api/grants/{topic_id}", response_model=GrantDetailResponse)
    def grant_detail(
        topic_id: str,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> GrantDetailResponse:
        request_id = x_request_id
        reference_time = datetime.now(timezone.utc)
        grants = app.state.app_state.get_grants() if hasattr(app.state.app_state, "get_grants") else []
        indexed_grant = next((grant for grant in grants if getattr(grant, "id", None) == topic_id), None)
        cached_live_grant = app.state.live_grant_cache.get_grant(request_id, topic_id, now=reference_time)
        try:
            detail = app.state.grant_detail_service.get(topic_id)
        except LookupError as exc:
            if cached_live_grant is not None:
                detail = build_grant_record_fallback(
                    cached_live_grant,
                    source="live_grant_cache_fallback",
                    detail_note="Using a search-summary fallback because official topic detail was unavailable.",
                )
            elif indexed_grant is not None:
                detail = build_grant_record_fallback(indexed_grant)
            else:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return app.state.translation_service.translate_grant_detail(
            detail,
            grant=cached_live_grant or indexed_grant,
        )

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
        reference_time = datetime.now(timezone.utc)
        request_id = resolve_request_id(x_request_id)
        bind_request_context(
            operation="match",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        status = sync_match_coordinator().get_status()
        if not is_match_ready(status):
            raise HTTPException(
                status_code=503,
                detail=build_match_unavailable_error(status, request_id=request_id),
            )
        execution = sync_match_coordinator().execute_match(
            payload.company_description,
            request_id=request_id,
            now=reference_time,
        )
        billing_available = active_settings.billing_enabled
        search_artifact_store = app.state.search_artifact_store
        fingerprint = _build_search_fingerprint(payload.company_description)
        artifact = search_artifact_store.create_from_execution(
            fingerprint=fingerprint,
            company_description=payload.company_description,
            execution=execution,
            now=reference_time,
        )
        try:
            access = app.state.billing_client.get_artifact_access(
                artifact_id=artifact.id,
                fingerprint=artifact.fingerprint,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except (BillingServiceUnavailableError, BillingServiceError) as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="get_artifact_access",
                request_id=request_id,
                fallback_used=True,
                context={"artifact_id": artifact.id},
            )
            billing_available = False
            access = ArtifactAccessPayload(has_access=False, status="billing_unavailable")
        response = build_preview_match_response(
            artifact=artifact,
            access=access,
            request_id=request_id,
            base_response=execution.match_response.model_copy(
                update={
                    "indexed_grants": len(execution.all_grants),
                    "refresh_indexed_grants": len(execution.all_grants),
                    "result_source": execution.result_source,
                }
            ),
        )
        return response.model_copy(update={"billing_available": billing_available})

    @app.post("/api/billing/guest-checkout", response_model=GuestCheckoutResponse)
    def guest_checkout(
        payload: GuestCheckoutRequest,
        request: Request,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> GuestCheckoutResponse:
        request_id = resolve_request_id(x_request_id)
        account_context = resolve_account_context(request)
        bind_request_context(
            operation="guest_checkout",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        try:
            email, fingerprint = _identity_for_request(
                account_context,
                email=payload.email,
                fingerprint=payload.fingerprint,
            )
            session = app.state.billing_client.create_guest_unlock_checkout(
                artifact_id=payload.artifact_id,
                fingerprint=fingerprint,
                email=email,
                account_context=account_context,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except BillingServiceError as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="create_guest_unlock_checkout",
                request_id=request_id,
                fallback_used=True,
                context={"artifact_id": payload.artifact_id},
            )
            raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc
        return GuestCheckoutResponse(checkout_url=session.checkout_url)

    @app.post("/api/billing/subscription-checkout", response_model=SubscriptionCheckoutResponse)
    def subscription_checkout(
        payload: SubscriptionCheckoutRequest,
        request: Request,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> SubscriptionCheckoutResponse:
        request_id = resolve_request_id(x_request_id)
        account_context = resolve_account_context(request)
        bind_request_context(
            operation="subscription_checkout",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        try:
            email, fingerprint = _identity_for_request(account_context, email=payload.email)
            session = app.state.billing_client.create_subscription_checkout(
                email=email,
                success_url=payload.success_url,
                cancel_url=payload.cancel_url,
                account_context=account_context,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except BillingServiceError as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="create_subscription_checkout",
                request_id=request_id,
                fallback_used=True,
                context={"email": payload.email},
            )
            raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc
        return SubscriptionCheckoutResponse(checkout_url=session.checkout_url)

    @app.get("/api/search-artifacts/{artifact_id}/access", response_model=ArtifactAccessResponse)
    def search_artifact_access(
        artifact_id: str,
        request: Request,
        email: str | None = None,
        fingerprint: str | None = None,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> ArtifactAccessResponse:
        request_id = resolve_request_id(x_request_id)
        account_context = resolve_account_context(request)
        bind_request_context(
            operation="artifact_access",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        try:
            email, fingerprint = _identity_for_request(
                account_context,
                email=email,
                fingerprint=fingerprint,
            )
            access = app.state.billing_client.get_artifact_access(
                artifact_id=artifact_id,
                email=email,
                fingerprint=fingerprint,
                account_context=account_context,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except BillingServiceError as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="get_artifact_access",
                request_id=request_id,
                fallback_used=True,
                context={"artifact_id": artifact_id},
            )
            raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc
        return _artifact_access_response(artifact_id, access)

    @app.post("/api/search-artifacts/{artifact_id}/unlock-with-credit", response_model=CreditUnlockResponse)
    def search_artifact_unlock_with_credit(
        artifact_id: str,
        payload: CreditUnlockRequest,
        request: Request,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> CreditUnlockResponse:
        request_id = resolve_request_id(x_request_id)
        account_context = resolve_account_context(request)
        bind_request_context(
            operation="artifact_credit_unlock",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        try:
            email, fingerprint = _identity_for_request(
                account_context,
                email=payload.email,
                fingerprint=payload.fingerprint,
            )
            consumed = app.state.billing_client.consume_credit_unlock(
                artifact_id=artifact_id,
                email=email,
                fingerprint=fingerprint,
                account_context=account_context,
            )
            access = app.state.billing_client.get_artifact_access(
                artifact_id=artifact_id,
                email=email,
                fingerprint=fingerprint,
                account_context=account_context,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except BillingServiceError as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="consume_credit_unlock",
                request_id=request_id,
                fallback_used=True,
                context={"artifact_id": artifact_id},
            )
            raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc
        return CreditUnlockResponse(
            artifact_id=artifact_id,
            consumed=consumed.consumed,
            has_access=getattr(access, "has_access", False),
            status=getattr(access, "status", "preview"),
            expires_at=getattr(access, "expires_at", None),
            access_state=_access_state_for_response(access),
        )

    @app.get("/api/account/dashboard", response_model=AccountDashboardResponse)
    def account_dashboard(
        email: str,
        request: Request,
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> AccountDashboardResponse:
        request_id = resolve_request_id(x_request_id)
        account_context = resolve_account_context(request)
        bind_request_context(
            operation="account_dashboard",
            request_id=request_id,
            model=active_settings.openai_match_model if active_settings.openai_api_key else None,
        )
        try:
            email_hint, _ = _identity_for_request(account_context, email=email)
            dashboard = app.state.billing_client.get_account_dashboard(
                email=email_hint,
                account_context=account_context,
            )
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
        except BillingServiceError as exc:
            capture_backend_exception(
                exc,
                component="billing",
                operation="get_account_dashboard",
                request_id=request_id,
                fallback_used=True,
                context={"email": email},
            )
            raise HTTPException(status_code=503, detail={"code": "BILLING_UNAVAILABLE"}) from exc
        return AccountDashboardResponse(
            credits_remaining=dashboard.credits_remaining,
            dashboard_url=dashboard.dashboard_url,
        )

    @app.post("/api/application-brief", response_model=ApplicationBriefResponse)
    def application_brief(
        payload: ApplicationBriefRequest,
        request: Request,
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
        account_context = resolve_account_context(request)
        require_artifact_access(
            billing_client=app.state.billing_client,
            artifact_id=payload.artifact_id,
            account_context=account_context,
            on_billing_error=lambda exc: capture_backend_exception(
                exc,
                component="billing",
                operation="get_artifact_access",
                request_id=request_id,
                fallback_used=True,
                context={"artifact_id": payload.artifact_id},
            ),
        )
        try:
            response = brief_service.generate(
                artifact_id=payload.artifact_id,
                company_description=payload.company_description,
                match_result=payload.match_result.model_dump(),
                grant_detail=payload.grant_detail.model_dump(),
            )
            sentry_sdk.set_measurement("application_brief_failed", 0.0)
            return response.model_copy(update={"request_id": request_id})
        except (BillingUnauthorizedError, BillingForbiddenError) as exc:
            raise http_exception_for_billing_error(exc) from exc
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

    if active_settings.sentry_debug_endpoint_enabled:

        @app.get("/sentry-debug")
        def sentry_debug() -> None:
            _ = 1 / 0

    return app


app = create_app()
