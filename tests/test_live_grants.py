from datetime import datetime, timezone

from backend.live_grants import LiveGrantService, LiveGrantRetrievalResult, generate_live_search_queries


def test_generate_live_search_queries_for_openai_profile_prioritizes_ai_queries():
    queries = generate_live_search_queries(
        (
            "We develop and deploy advanced AI systems including large language models, image generation, "
            "and reasoning engines. We focus on AI safety research and enterprise AI deployment."
        )
    )

    assert "artificial intelligence" in queries
    assert "AI safety" in queries
    assert "foundation models" in queries or "large language models" in queries


def test_generate_live_search_queries_for_digital_health_profile_prioritizes_health_queries():
    queries = generate_live_search_queries(
        (
            "We build digital health infrastructure connecting patients with healthcare professionals. "
            "Our platform supports telemedicine and secure health data exchange."
        )
    )

    assert "digital health" in queries
    assert "telemedicine" in queries
    assert "health data" in queries


def test_live_grant_service_filters_irrelevant_and_duplicate_results():
    class FakeClient:
        def search(self, *, text: str, page_number: int = 1, page_size: int = 25) -> dict:
            if text == "artificial intelligence":
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Apply AI for hospitals"],
                                "identifier": ["TOPIC-1"],
                                "callIdentifier": ["DIGITAL-2026-AI-01"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                                "keywords": ["Artificial intelligence", "digital health"],
                                "description": ["AI deployment in clinical settings."],
                                "frameworkProgramme": ["Digital Europe Programme"],
                            }
                        },
                        {
                            "metadata": {
                                "title": ["Apply AI for hospitals duplicate"],
                                "identifier": ["TOPIC-1"],
                                "callIdentifier": ["DIGITAL-2026-AI-01"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                                "keywords": ["Artificial intelligence"],
                                "description": ["Duplicate entry."],
                                "frameworkProgramme": ["Digital Europe Programme"],
                            }
                        },
                        {
                            "metadata": {
                                "title": ["Battery recycling topic"],
                                "identifier": ["TOPIC-2"],
                                "callIdentifier": ["LIFE-2026-02"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                                "keywords": ["battery recycling"],
                                "description": ["Circular economy for battery materials."],
                                "frameworkProgramme": ["LIFE Programme"],
                            }
                        },
                    ],
                    "totalResults": 3,
                }
            return {"results": [], "totalResults": 0}

    service = LiveGrantService(client=FakeClient())

    result = service.retrieve(
        "We build AI systems for hospital deployment and digital health workflows.",
        queries=["artificial intelligence"],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert isinstance(result, LiveGrantRetrievalResult)
    assert [grant.id for grant in result.grants] == ["TOPIC-1"]
    assert result.source == "live_retrieval"
    assert result.degradation_reasons == []
