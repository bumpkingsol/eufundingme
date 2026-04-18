import json

from backend.normalize import normalize_grant


def test_normalize_uses_first_value_from_array_fields():
    metadata = {
        "title": ["Grant title"],
        "identifier": ["TOPIC-123"],
        "status": ["31094501"],
        "deadlineDate": ["2026-08-01T17:00:00Z"],
        "keywords": ["ai", "safety"],
    }

    record = normalize_grant(metadata)

    assert record.id == "TOPIC-123"
    assert record.title == "Grant title"
    assert record.status == "Open"
    assert record.deadline == "2026-08-01"
    assert record.portal_url.endswith("/TOPIC-123")
    assert record.keywords == ["ai", "safety"]


def test_normalize_accepts_dict_wrapped_scalars():
    metadata = {
        "title": {"0": "European Battery Grant"},
        "identifier": {"0": "BATTERY-9"},
        "status": {"0": "31094502"},
        "frameworkProgramme": {"0": "Horizon Europe"},
        "programmeDivision": {"0": "Cluster 5"},
    }

    record = normalize_grant(metadata)

    assert record.id == "BATTERY-9"
    assert record.status == "Forthcoming"
    assert "horizon europe" in record.search_text
    assert "cluster 5" in record.search_text


def test_normalize_extracts_budget_from_budget_overview():
    budget_overview = {
        "budgetTopicActionMap": {
            "123": [
                {
                    "action": "TOPIC-123",
                    "budgetYearMap": {
                        "2026": "5000000",
                        "2027": "1200000",
                    },
                }
            ]
        }
    }
    metadata = {
        "title": ["Grant title"],
        "identifier": ["TOPIC-123"],
        "status": ["31094501"],
        "budgetOverview": [json.dumps(budget_overview)],
    }

    record = normalize_grant(metadata)

    assert record.budget_amount_eur == 6200000
    assert record.budget_display == "EUR 6.2M"


def test_normalize_handles_malformed_budget_without_crashing():
    metadata = {
        "title": ["Grant title"],
        "identifier": ["TOPIC-123"],
        "status": ["31094501"],
        "budgetOverview": ["{not-json"],
    }

    record = normalize_grant(metadata)

    assert record.budget_amount_eur is None
    assert record.budget_display is None


def test_normalize_derives_human_programme_labels_from_identifier_when_upstream_values_are_numeric():
    metadata = {
        "title": ["Frontier AI Grant"],
        "identifier": ["HORIZON-CL4-2027-04-DIGITAL-EMERGING-11"],
        "callIdentifier": ["HORIZON-CL4-2027-04"],
        "status": ["31094501"],
        "frameworkProgramme": ["43108390"],
        "programmeDivision": ["43108541"],
        "keywords": [
            "HORIZON-CL4-2027-04-DIGITAL-EMERGING-11",
            "HORIZON-CL4-2027-04",
            "Artificial intelligence",
        ],
    }

    record = normalize_grant(metadata)

    assert record.framework_programme == "Horizon Europe"
    assert record.programme_division == "Cluster 4"
    assert record.keywords == ["Artificial intelligence"]


def test_normalize_keeps_useful_keywords_and_dedupes_noise():
    metadata = {
        "title": ["Battery Grant"],
        "identifier": ["BATTERY-2027-01"],
        "callIdentifier": ["BATTERY-2027"],
        "status": ["31094501"],
        "keywords": [
            "BATTERY-2027-01",
            "BATTERY-2027",
            "Circular economy",
            "Circular economy",
            "Waste recycling",
        ],
    }

    record = normalize_grant(metadata)

    assert record.keywords == ["Circular economy", "Waste recycling"]
