from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import Settings
from backend.models import GrantRecord
from backend.snapshot_store import IndexSnapshotStore
from backend.state import AppState


def make_grant(grant_id: str) -> GrantRecord:
    return GrantRecord(
        id=grant_id,
        title=f"Grant {grant_id}",
        status="Open",
        portal_url=f"https://example.com/{grant_id}",
        deadline="2026-08-01",
        deadline_at=datetime(2026, 8, 1, 17, 0, tzinfo=timezone.utc),
        framework_programme="Horizon Europe",
        programme_division="Cluster 4",
        keywords=["ai"],
        search_text="ai",
    )


def make_settings(snapshot_path: Path) -> Settings:
    return Settings(
        index_snapshot_path=str(snapshot_path),
        index_snapshot_max_age_hours=24,
        index_refresh_stall_seconds=60,
    )


def test_app_state_loads_snapshot_and_marks_matching_available(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    settings = make_settings(snapshot_path)
    snapshot_store = IndexSnapshotStore(snapshot_path)
    saved_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    snapshot_store.save(
        grants=[make_grant("TOPIC-1")],
        embeddings={"TOPIC-1": [0.1, 0.2]},
        status_payload={
            "phase": "ready_degraded",
            "message": "Index ready with degraded coverage or matching quality",
            "indexed_grants": 1,
            "scanned_prefixes": 1,
            "total_prefixes": 1,
            "failed_prefixes": 0,
            "truncated_prefixes": 0,
            "embeddings_ready": True,
            "degraded": True,
            "coverage_complete": True,
            "matching_available": True,
            "degradation_reasons": ["lexical_only_mode"],
        },
        written_at=saved_at,
    )

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.phase == "ready_degraded"
    assert status.matching_available is True
    assert status.snapshot_loaded is True
    assert status.snapshot_age_seconds is not None
    assert "stale_snapshot_mode" in status.degradation_reasons
    assert state.get_grants()[0].id == "TOPIC-1"


def test_app_state_ignores_invalid_snapshot(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    snapshot_path.write_text("{not-json", encoding="utf-8")
    settings = make_settings(snapshot_path)

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.phase == "idle"
    assert status.matching_available is False
    assert status.snapshot_loaded is False


def test_app_state_preserves_snapshot_during_refresh_failure(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    settings = make_settings(snapshot_path)
    snapshot_store = IndexSnapshotStore(snapshot_path)
    snapshot_store.save(
        grants=[make_grant("TOPIC-1")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Index ready",
            "indexed_grants": 1,
            "scanned_prefixes": 1,
            "total_prefixes": 1,
            "failed_prefixes": 0,
            "truncated_prefixes": 0,
            "embeddings_ready": False,
            "degraded": False,
            "coverage_complete": True,
            "matching_available": True,
            "degradation_reasons": [],
        },
    )

    class BrokenClient:
        def search(self, *, text: str, page_number: int, page_size: int) -> dict:
            raise RuntimeError("boom")

    state = AppState(settings=settings, client=BrokenClient(), prefixes=["AI-2026"])
    state.ensure_indexing_started()
    assert state._thread is not None
    state._thread.join(timeout=5)

    status = state.get_status()
    assert status.matching_available is True
    assert status.refresh_in_progress is False
    assert status.snapshot_loaded is True
    assert "stale_snapshot_mode" in status.degradation_reasons
    assert "prefix_fetch_failed" in status.degradation_reasons
