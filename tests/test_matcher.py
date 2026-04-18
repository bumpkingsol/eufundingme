from datetime import datetime, timezone

from backend.embeddings import cosine_similarity, lexical_shortlist
from backend.matcher import MatchService, OpenAIScorer
from backend.models import GrantRecord, MatchCandidate, ParsedLLMMatch


def make_grant(grant_id: str, title: str, *, keywords: list[str]) -> GrantRecord:
    return GrantRecord(
        id=grant_id,
        title=title,
        status="Open",
        portal_url=f"https://example.com/{grant_id}",
        deadline="2026-08-01",
        deadline_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        keywords=keywords,
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        search_text=f"{title} {' '.join(keywords)} horizon europe cluster 4".lower(),
    )


def test_cosine_similarity_returns_one_for_identical_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_lexical_shortlist_prefers_overlap():
    grants = [
        make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"]),
        make_grant("TOPIC-2", "Battery Materials", keywords=["battery", "recycling"]),
    ]

    candidates = lexical_shortlist("We build AI safety tooling.", grants, limit=2)

    assert [candidate.grant.id for candidate in candidates] == ["TOPIC-1"]


def test_lexical_shortlist_ignores_stopwords_and_generic_business_terms():
    grants = [
        make_grant(
            "TOPIC-1",
            "Trustworthy Foundation Models for European Industry",
            keywords=["ai", "foundation models", "safety", "enterprise"],
        ),
        make_grant(
            "TOPIC-2",
            "Support to Dissemination and Exploitation for the Digital Europe Programme",
            keywords=["solutions", "digital"],
        ),
    ]

    candidates = lexical_shortlist(
        "We build enterprise healthcare solutions for companies and governments across the EU",
        grants,
        limit=5,
    )

    assert candidates == []


def test_match_service_clamps_ai_scores():
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.9)
        ],
        scorer=lambda company_description, candidates: [
            ParsedLLMMatch(
                grant_id="TOPIC-1",
                fit_score=180,
                why_match="Strong overlap in applied AI safety.",
                application_angle="Lead with trusted deployment across Europe.",
            )
        ],
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].fit_score == 100


def test_match_service_falls_back_when_scorer_fails():
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.75)
        ],
        scorer=lambda company_description, candidates: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].grant_id == "TOPIC-1"
    assert response.results[0].fit_score >= 70
    assert "ai" in response.results[0].why_match.lower()


def test_match_service_reports_scorer_failures():
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])
    captured = []

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.75)
        ],
        scorer=lambda company_description, candidates: (_ for _ in ()).throw(RuntimeError("boom")),
        on_scorer_failure=lambda exc, *, context: captured.append((str(exc), context)),
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].grant_id == "TOPIC-1"
    assert captured == [(
        "boom",
        {
            "candidate_count": 1,
            "grant_count": 1,
            "fallback_used": True,
        },
    )]


def test_openai_scorer_uses_responses_api_with_reasoning_effort():
    class FakeResponses:
        def __init__(self) -> None:
            self.calls = []

        def parse(self, **kwargs):
            self.calls.append(kwargs)
            return type(
                "ParsedResponse",
                (),
                {
                    "output_parsed": type(
                        "ParsedPayload",
                        (),
                        {
                            "matches": [
                                ParsedLLMMatch(
                                    grant_id="TOPIC-1",
                                    fit_score=91,
                                    why_match="Strong overlap in applied AI safety.",
                                    application_angle="Lead with trusted deployment across Europe.",
                                )
                            ]
                        },
                    )()
                },
            )()

    fake_responses = FakeResponses()
    fake_client = type("FakeClient", (), {"responses": fake_responses})()
    scorer = OpenAIScorer(
        model="gpt-5.4-mini-2026-03-17",
        client=fake_client,
        reasoning_effort="low",
    )
    candidates = [MatchCandidate(grant=make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai"]), shortlist_score=0.9)]

    parsed = scorer.score("We build AI safety tooling.", candidates)

    assert parsed[0].grant_id == "TOPIC-1"
    assert fake_responses.calls[0]["model"] == "gpt-5.4-mini-2026-03-17"
    assert fake_responses.calls[0]["reasoning"] == {"effort": "low"}
    instructions = fake_responses.calls[0]["instructions"]
    assert "specific grant requirements" in instructions
    assert "specific company capabilities" in instructions


def test_match_service_emits_sentry_spans_and_measurements(monkeypatch):
    class FakeSpan:
        def __init__(self, op: str, name: str) -> None:
            self.op = op
            self.name = name
            self.data = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def set_data(self, key: str, value) -> None:
            self.data[key] = value

    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])
    spans = []
    measurements = []
    perf_counter_values = iter([100.0, 100.25])

    monkeypatch.setattr(
        "backend.matcher.sentry_sdk.start_span",
        lambda *, op, name: spans.append(FakeSpan(op, name)) or spans[-1],
    )
    monkeypatch.setattr(
        "backend.matcher.sentry_sdk.set_measurement",
        lambda name, value: measurements.append((name, value)),
    )
    monkeypatch.setattr(
        "backend.matcher.time.perf_counter",
        lambda: next(perf_counter_values),
    )

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.9)
        ],
        scorer=lambda company_description, candidates: [
            ParsedLLMMatch(
                grant_id="TOPIC-1",
                fit_score=92,
                why_match="Strong overlap in applied AI safety.",
                application_angle="Lead with trusted deployment across Europe.",
            )
        ],
    )

    response = service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert response.results[0].grant_id == "TOPIC-1"
    assert [(span.op, span.name) for span in spans] == [
        ("ai.shortlist", "Candidate shortlist"),
        ("ai.score", "LLM candidate scoring"),
    ]
    assert spans[0].data == {"grant_count": 1, "candidate_count": 1}
    assert spans[1].data == {"candidate_count": 1, "matches_returned": 1}
    assert ("grants_indexed", 1) in measurements
    assert ("match_latency_ms", 250.0) in measurements


def test_match_service_preserves_core_measurements_without_embedding_metric_shortcuts(monkeypatch):
    grant = make_grant("TOPIC-1", "AI Safety Grant", keywords=["ai", "safety"])
    measurements = []

    monkeypatch.setattr(
        "backend.matcher.sentry_sdk.start_span",
        lambda **kwargs: type(
            "Span",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, exc_type, exc, tb: False,
                "set_data": lambda self, key, value: None,
            },
        )(),
    )
    monkeypatch.setattr(
        "backend.matcher.sentry_sdk.set_measurement",
        lambda name, value: measurements.append((name, value)),
    )

    service = MatchService(
        shortlister=lambda company_description, grants, limit: [
            MatchCandidate(grant=grant, shortlist_score=0.9)
        ],
        scorer=None,
    )

    service.match(
        "We build AI safety tooling.",
        [grant],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert ("grants_indexed", 1) in measurements
    assert any(name == "match_latency_ms" for name, _ in measurements)
    assert all(name != "embedding_cache_hit_rate" for name, _ in measurements)
