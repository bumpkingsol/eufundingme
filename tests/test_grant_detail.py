from backend.grant_detail import normalize_topic_detail_payload


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
