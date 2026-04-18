from datetime import datetime, timezone

import requests

from backend.ec_client import ECSearchClient
from backend.indexer import build_grant_index, filter_indexable_grants
from backend.models import GrantRecord


def make_grant(grant_id: str, status: str, deadline: str | None) -> GrantRecord:
    deadline_at = None
    if deadline:
        deadline_at = datetime.fromisoformat(f"{deadline}T17:00:00+00:00")
    return GrantRecord(
        id=grant_id,
        title=grant_id,
        status=status,
        portal_url=f"https://example.com/{grant_id}",
        deadline=deadline,
        deadline_at=deadline_at,
        search_text=grant_id.lower(),
    )


def test_filter_indexable_grants_keeps_only_open_future_unique_grants():
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    results = [
        make_grant("TOPIC-1", "Open", "2026-08-01"),
        make_grant("TOPIC-1", "Open", "2026-08-01"),
        make_grant("TOPIC-2", "Closed", "2026-08-01"),
        make_grant("TOPIC-3", "Open", "2025-01-01"),
        make_grant("TOPIC-4", "Forthcoming", None),
    ]

    kept = filter_indexable_grants(results, now=now)

    assert [grant.id for grant in kept] == ["TOPIC-1", "TOPIC-4"]


def test_build_grant_index_merges_prefix_results_and_dedupes():
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            self.calls.append((text, page_number))
            if text == "AI-2026":
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["AI Grant"],
                                "identifier": ["TOPIC-1"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                            }
                        }
                    ],
                    "totalResults": 1,
                }
            if text == "BATTERY-2026":
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Battery Grant"],
                                "identifier": ["TOPIC-2"],
                                "status": ["31094502"],
                            }
                        },
                        {
                            "metadata": {
                                "title": ["AI Grant Duplicate"],
                                "identifier": ["TOPIC-1"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                            }
                        },
                    ],
                    "totalResults": 2,
                }
            return {"results": [], "totalResults": 0}

    client = FakeClient()

    grants, build_details = build_grant_index(
        client=client,
        prefixes=["AI-2026", "BATTERY-2026"],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert [grant.id for grant in grants] == ["TOPIC-1", "TOPIC-2"]
    assert client.calls == [("AI-2026", 1), ("BATTERY-2026", 1)]
    assert build_details.failed_prefixes == 0


def test_filter_indexable_grants_prefers_higher_quality_duplicate_record():
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    low_quality = GrantRecord(
        id="TOPIC-1",
        title="AI Grant",
        status="Open",
        portal_url="https://example.com/TOPIC-1",
        deadline="2026-08-01",
        deadline_at=datetime.fromisoformat("2026-08-01T17:00:00+00:00"),
        framework_programme="43108390",
        programme_division="43108541",
        keywords=["TOPIC-1"],
        search_text="ai grant",
    )
    high_quality = GrantRecord(
        id="TOPIC-1",
        title="AI Grant",
        status="Open",
        portal_url="https://example.com/topic-details/TOPIC-1",
        deadline="2026-08-01",
        deadline_at=datetime.fromisoformat("2026-08-01T17:00:00+00:00"),
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        keywords=["Artificial intelligence"],
        search_text="ai grant artificial intelligence",
    )

    kept = filter_indexable_grants([low_quality, high_quality], now=now)

    assert len(kept) == 1
    assert kept[0].framework_programme == "Horizon Europe"
    assert kept[0].keywords == ["Artificial intelligence"]


def test_build_grant_index_crawls_multiple_pages_until_exhausted():
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            self.calls.append((text, page_number))
            if text != "AI-2026":
                return {"results": [], "totalResults": 0}
            if page_number == 1:
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Grant 1"],
                                "identifier": ["TOPIC-1"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                            }
                        }
                    ],
                    "totalResults": 2,
                }
            if page_number == 2:
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Grant 2"],
                                "identifier": ["TOPIC-2"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-02T17:00:00Z"],
                            }
                        }
                    ],
                    "totalResults": 2,
                }
            return {"results": [], "totalResults": 2}

    grants, build_details = build_grant_index(
        client=FakeClient(),
        prefixes=["AI-2026"],
        page_size=1,
        max_pages_per_prefix=None,
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert [grant.id for grant in grants] == ["TOPIC-1", "TOPIC-2"]
    assert build_details.failed_prefixes == 0


def test_build_grant_index_marks_truncated_prefixes_when_page_cap_is_hit():
    class FakeClient:
        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            return {
                "results": [
                    {
                        "metadata": {
                            "title": [f"Grant {page_number}"],
                            "identifier": [f"TOPIC-{page_number}"],
                            "status": ["31094501"],
                            "deadlineDate": ["2026-08-01T17:00:00Z"],
                        }
                    }
                ],
                "totalResults": 3,
            }

    grants, build_details = build_grant_index(
        client=FakeClient(),
        prefixes=["AI-2026"],
        page_size=1,
        max_pages_per_prefix=2,
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert [grant.id for grant in grants] == ["TOPIC-1", "TOPIC-2"]
    assert build_details.truncated_prefixes == 1
    assert build_details.failed_prefixes == 0
    assert build_details.degradation_reasons == ["crawl_truncated"]


def test_build_grant_index_reports_failed_prefixes_without_raising():
    class FakeClient:
        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            if text == "BROKEN-2026":
                raise RuntimeError("boom")
            return {
                "results": [
                    {
                        "metadata": {
                            "title": ["Healthy Grant"],
                            "identifier": ["TOPIC-1"],
                            "status": ["31094501"],
                            "deadlineDate": ["2026-08-01T17:00:00Z"],
                        }
                    }
                ],
                "totalResults": 1,
            }

    grants, build_details = build_grant_index(
        client=FakeClient(),
        prefixes=["BROKEN-2026", "HEALTHY-2026"],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert [grant.id for grant in grants] == ["TOPIC-1"]
    assert build_details.failed_prefixes == 1
    assert build_details.degradation_reasons == ["prefix_fetch_failed"]


def test_build_grant_index_reports_progress_for_each_page():
    class FakeClient:
        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            if page_number == 1:
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Grant 1"],
                                "identifier": ["TOPIC-1"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-01T17:00:00Z"],
                            }
                        }
                    ],
                    "totalResults": 2,
                }
            if page_number == 2:
                return {
                    "results": [
                        {
                            "metadata": {
                                "title": ["Grant 2"],
                                "identifier": ["TOPIC-2"],
                                "status": ["31094501"],
                                "deadlineDate": ["2026-08-02T17:00:00Z"],
                            }
                        }
                    ],
                    "totalResults": 2,
                }
            return {"results": [], "totalResults": 2}

    progress_events = []

    build_grant_index(
        client=FakeClient(),
        prefixes=["AI-2026"],
        page_size=1,
        max_pages_per_prefix=None,
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
        progress_callback=progress_events.append,
    )

    assert len(progress_events) == 3
    assert progress_events[0].current_prefix == "AI-2026"
    assert progress_events[0].current_page == 1
    assert progress_events[0].pages_fetched == 1
    assert progress_events[0].scanned_prefixes == 0
    assert progress_events[1].current_page == 2
    assert progress_events[1].pages_fetched == 2
    assert progress_events[1].requests_completed == 2
    assert progress_events[2].scanned_prefixes == 1


def test_ec_search_client_retries_transient_request_failures():
    class FakeSession:
        def __init__(self) -> None:
            self.attempts = 0

        def post(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise requests.Timeout("slow")
            return FakeResponse({"results": [], "totalResults": 0})

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    client = ECSearchClient(session=FakeSession(), timeout_seconds=1.0, max_retries=2, retry_backoff_seconds=0.0)

    payload = client.search(text="AI-2026")

    assert payload == {"results": [], "totalResults": 0}
    assert client.session.attempts == 3
