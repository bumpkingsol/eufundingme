from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import load_settings


SETTINGS = load_settings()

pytestmark = pytest.mark.skipif(
    not SETTINGS.openai_api_key or os.getenv("OPENAI_LIVE_SMOKE") != "1",
    reason="requires OPENAI_API_KEY via app settings and OPENAI_LIVE_SMOKE=1",
)


def test_openai_http_runtime_smoke() -> None:
    client = TestClient(create_app())
    request_id = "live-smoke-anthropic"

    profile_response = client.post(
        "/api/profile/resolve",
        json={"query": "Anthropic"},
        headers={"X-Request-ID": request_id},
    )
    assert profile_response.status_code == 200
    profile_payload = profile_response.json()
    assert profile_payload["resolved"] is True
    assert profile_payload["source"] in {"llm_expansion", "demo_profile"}
    assert len(profile_payload["profile"]) > 40

    website_response = client.post(
        "/api/profile/from-website",
        json={"url": "anthropic.com"},
        headers={"X-Request-ID": request_id},
    )
    assert website_response.status_code == 200
    website_payload = website_response.json()
    assert website_payload["resolved"] is True
    assert website_payload["source"] == "website_profile"
    assert website_payload["normalized_url"] == "https://anthropic.com"
    assert len(website_payload["profile"]) > 40

    match_response = client.post(
        "/api/match",
        json={
            "company_description": (
                "Anthropic is a European-facing AI research and product company building frontier "
                "language models, AI safety systems, developer APIs, and enterprise AI tooling "
                "for regulated industries."
            )
        },
        headers={"X-Request-ID": request_id},
    )
    assert match_response.status_code == 200
    match_payload = match_response.json()
    assert match_payload["result_source"] == "live_retrieval"
    assert match_payload["results"]

    top_result = match_payload["results"][0]
    detail_response = client.get(
        f"/api/grants/{top_result['grant_id']}",
        headers={"X-Request-ID": request_id},
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["grant_id"] == top_result["grant_id"]
    assert detail_payload["full_description"] or detail_payload["detail_note"]

    brief_response = client.post(
        "/api/application-brief",
        json={
            "company_description": (
                "Anthropic is a European-facing AI research and product company building frontier "
                "language models, AI safety systems, developer APIs, and enterprise AI tooling "
                "for regulated industries."
            ),
            "match_result": top_result,
            "grant_detail": detail_payload,
        },
        headers={"X-Request-ID": request_id},
    )
    assert brief_response.status_code == 200
    brief_payload = brief_response.json()
    assert "application brief" in brief_payload["markdown"].lower()
