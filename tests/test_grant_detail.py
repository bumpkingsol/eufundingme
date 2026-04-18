from backend.grant_detail import normalize_topic_detail_payload
from backend.models import GrantRecord
from backend.translation import GrantTranslationService


def test_normalize_topic_detail_payload_extracts_application_sections():
    payload = {
        "topicDetails": {
            "summary": {
                "title": "AI Factories",
                "identifier": "DIGITAL-2026-AI-01",
                "deadlineDate": "2026-10-15T17:00:00Z",
            },
            "sections": {
                "objective": "<p>Build AI capacity across Europe.</p>",
                "expectedOutcomes": [
                    "<p>Deploy shared compute capacity.</p>",
                    "<p>Support SME access.</p>",
                ],
                "eligibilityConditions": "<ul><li>EU legal entities</li><li>Consortium of 3+</li></ul>",
                "submissionConditions": {
                    "deadlineDate": "2026-10-15T17:00:00Z",
                    "deadlineModel": "single-stage",
                },
                "documents": [
                    {
                        "title": "Work Programme",
                        "url": "https://example.com/work-programme.pdf",
                    }
                ],
                "partnerSearch": True,
            },
        }
    }

    detail = normalize_topic_detail_payload(payload, topic_id="DIGITAL-2026-AI-01")

    assert detail.grant_id == "DIGITAL-2026-AI-01"
    assert detail.full_description == "Build AI capacity across Europe."
    assert detail.expected_outcomes == [
        "Deploy shared compute capacity.",
        "Support SME access.",
    ]
    assert detail.eligibility_criteria == [
        "EU legal entities",
        "Consortium of 3+",
    ]
    assert detail.submission_deadlines == [
        {
            "label": "Main deadline",
            "value": "2026-10-15",
        }
    ]
    assert detail.documents == [
        {
            "title": "Work Programme",
            "url": "https://example.com/work-programme.pdf",
        }
    ]
    assert detail.partner_search_available is True
    assert detail.fallback_used is False


def test_grant_detail_translation_service_translates_non_english_detail_text():
    payload = {
        "topicDetails": {
            "summary": {
                "identifier": "BG-TOPIC-1",
                "deadlineDate": "2026-10-15T17:00:00Z",
            },
            "sections": {
                "objective": "<p>Национална програма за иновации в България.</p>",
                "expectedOutcomes": ["<p>Подкрепа за МСП.</p>"],
                "eligibilityConditions": "<ul><li>Български юридически лица</li></ul>",
                "documents": [
                    {
                        "title": "Насоки",
                        "url": "https://example.com/guide.pdf",
                    }
                ],
            },
        }
    }
    detail = normalize_topic_detail_payload(payload, topic_id="BG-TOPIC-1")
    grant = GrantRecord(
        id="BG-TOPIC-1",
        title="Национална програма",
        status="Open",
        portal_url="https://example.com/BG-TOPIC-1",
        source_language="bg",
        description="Програма за България",
        keywords=[],
        search_text="innovation",
    )
    service = GrantTranslationService(
        translator=lambda source_language, texts: [
            "National innovation programme in Bulgaria.",
            "Bulgarian legal entities",
            "Support for SMEs.",
            "Guidance",
        ]
    )

    translated = service.translate_grant_detail(detail, grant=grant)

    assert translated.full_description == "National innovation programme in Bulgaria."
    assert translated.eligibility_criteria == ["Bulgarian legal entities"]
    assert translated.expected_outcomes == ["Support for SMEs."]
    assert translated.documents == [{"title": "Guidance", "url": "https://example.com/guide.pdf"}]
    assert translated.source_language == "bg"
    assert translated.translated_from_source is True
    assert "Bulgaria" in translated.translation_note
