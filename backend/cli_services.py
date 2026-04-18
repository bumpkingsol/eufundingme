from __future__ import annotations

from datetime import datetime, timezone

from .app import create_app


def run_match_query(company_description: str):
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    status = app.state.app_state.get_status()
    grants = app.state.app_state.get_grants()
    result = app.state.match_service.match(
        company_description,
        grants,
        now=datetime.now(timezone.utc),
        limit=app.state.settings.shortlist_limit,
    )

    return {
        "indexed_grants": result.indexed_grants,
        "results": result.model_dump()["results"],
        "status": status.model_dump(),
    }


def run_index_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    status = app.state.app_state.get_status()

    return status.model_dump()


def run_status_query() -> dict:
    app = create_app()
    app.state.app_state.ensure_indexing_started()
    return app.state.app_state.get_status().model_dump()


def run_profile_query(query: str) -> dict:
    app = create_app()
    resolution = app.state.profile_resolver.resolve(query)
    return {
        "resolved": resolution.resolved,
        "profile": resolution.profile,
        "display_name": resolution.display_name,
        "source": resolution.source,
        "message": resolution.message,
    }
