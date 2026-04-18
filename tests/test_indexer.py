from datetime import datetime, timezone

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

    grants = build_grant_index(
        client=client,
        prefixes=["AI-2026", "BATTERY-2026"],
        now=datetime(2026, 4, 18, tzinfo=timezone.utc),
    )

    assert [grant.id for grant in grants] == ["TOPIC-1", "TOPIC-2"]
    assert client.calls == [("AI-2026", 1), ("BATTERY-2026", 1)]


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
