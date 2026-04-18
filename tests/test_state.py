from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import Settings
from backend.models import GrantRecord, IndexBuildDetails
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
        index_seed_snapshot_path=str(snapshot_path.parent / "grant-index.seed.json"),
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
    assert status.snapshot_source == "runtime"
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
    assert status.snapshot_source is None


def test_app_state_loads_bundled_seed_when_runtime_snapshot_missing(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    seed_path = tmp_path / "grant-index.seed.json"
    settings = make_settings(snapshot_path)
    snapshot_store = IndexSnapshotStore(seed_path)
    saved_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    snapshot_store.save(
        grants=[make_grant("TOPIC-SEED")],
        embeddings={"TOPIC-SEED": [0.1, 0.2]},
        status_payload={
            "phase": "ready",
            "message": "Index ready",
            "indexed_grants": 1,
            "scanned_prefixes": 1,
            "total_prefixes": 1,
            "failed_prefixes": 0,
            "truncated_prefixes": 0,
            "embeddings_ready": True,
            "degraded": False,
            "coverage_complete": True,
            "matching_available": True,
            "degradation_reasons": [],
        },
        written_at=saved_at,
    )

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.phase == "ready_degraded"
    assert status.matching_available is True
    assert status.snapshot_loaded is True
    assert status.snapshot_source == "bundled"
    assert status.embeddings_ready is True
    assert "bundled_seed_mode" in status.degradation_reasons
    assert state.get_grants()[0].id == "TOPIC-SEED"
    assert state.get_grant_embeddings() == {"TOPIC-SEED": [0.1, 0.2]}


def test_app_state_uses_bundled_seed_when_runtime_snapshot_invalid(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    snapshot_path.write_text("{not-json", encoding="utf-8")
    seed_path = tmp_path / "grant-index.seed.json"
    settings = make_settings(snapshot_path)
    snapshot_store = IndexSnapshotStore(seed_path)
    snapshot_store.save(
        grants=[make_grant("TOPIC-SEED")],
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

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.snapshot_loaded is True
    assert status.snapshot_source == "bundled"
    assert status.embeddings_ready is False
    assert state.get_grants()[0].id == "TOPIC-SEED"
    assert state.get_grant_embeddings() == {}


def test_app_state_prefers_bundled_seed_when_it_has_more_grants_than_runtime_snapshot(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    seed_path = tmp_path / "grant-index.seed.json"
    settings = make_settings(snapshot_path)

    IndexSnapshotStore(snapshot_path).save(
        grants=[make_grant("TOPIC-RUNTIME")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Runtime index ready",
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
        written_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    IndexSnapshotStore(seed_path).save(
        grants=[make_grant("TOPIC-SEED-1"), make_grant("TOPIC-SEED-2")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Bundled seed ready",
            "indexed_grants": 2,
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
        written_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.snapshot_loaded is True
    assert status.snapshot_source == "bundled"
    assert [grant.id for grant in state.get_grants()] == ["TOPIC-SEED-1", "TOPIC-SEED-2"]


def test_app_state_prefers_runtime_snapshot_when_it_is_at_least_as_large_as_bundled_seed(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    seed_path = tmp_path / "grant-index.seed.json"
    settings = make_settings(snapshot_path)

    IndexSnapshotStore(snapshot_path).save(
        grants=[make_grant("TOPIC-RUNTIME-1"), make_grant("TOPIC-RUNTIME-2")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Runtime index ready",
            "indexed_grants": 2,
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
        written_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    IndexSnapshotStore(seed_path).save(
        grants=[make_grant("TOPIC-SEED-1")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Bundled seed ready",
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
        written_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    state = AppState(settings=settings, prefixes=["AI-2026"])
    status = state.get_status()

    assert status.snapshot_loaded is True
    assert status.snapshot_source == "runtime"
    assert [grant.id for grant in state.get_grants()] == ["TOPIC-RUNTIME-1", "TOPIC-RUNTIME-2"]


def test_app_state_retains_snapshot_when_live_refresh_is_smaller(monkeypatch, tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    seed_path = tmp_path / "grant-index.seed.json"
    settings = make_settings(snapshot_path)

    IndexSnapshotStore(seed_path).save(
        grants=[make_grant("TOPIC-SEED-1"), make_grant("TOPIC-SEED-2")],
        embeddings={},
        status_payload={
            "phase": "ready",
            "message": "Bundled seed ready",
            "indexed_grants": 2,
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
        written_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )

    def fake_build_grant_index(**_kwargs):
        return [make_grant("TOPIC-LIVE")], IndexBuildDetails(
            failed_prefixes=0,
            truncated_prefixes=0,
            degradation_reasons=[],
        )

    monkeypatch.setattr("backend.state.build_grant_index", fake_build_grant_index)

    state = AppState(settings=settings, prefixes=["AI-2026"])
    state.ensure_indexing_started()
    assert state._thread is not None
    state._thread.join(timeout=5)

    status = state.get_status()
    assert status.snapshot_loaded is True
    assert status.snapshot_source == "bundled"
    assert status.indexed_grants == 2
    assert status.refresh_indexed_grants == 1
    assert status.phase == "ready_degraded"
    assert "live_refresh_smaller_than_snapshot" in status.degradation_reasons
    assert [grant.id for grant in state.get_grants()] == ["TOPIC-SEED-1", "TOPIC-SEED-2"]
    assert not snapshot_path.exists()


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
    assert status.snapshot_source == "runtime"
    assert "stale_snapshot_mode" in status.degradation_reasons
    assert "prefix_fetch_failed" in status.degradation_reasons


def test_app_state_builds_index_summary_from_grants(tmp_path):
    settings = make_settings(tmp_path / "grant-index.json")
    state = AppState(settings=settings, prefixes=["AI-2026"])
    state._grants = [
        make_grant("TOPIC-1"),
        GrantRecord(
            id="TOPIC-2",
            title="Grant TOPIC-2",
            status="Open",
            portal_url="https://example.com/TOPIC-2",
            deadline="2026-07-20",
            deadline_at=datetime(2026, 7, 20, 17, 0, tzinfo=timezone.utc),
            framework_programme="Digital Europe",
            programme_division="AI",
            budget_display="EUR 2M",
            budget_amount_eur=2_000_000,
            keywords=["digital"],
            search_text="digital",
        ),
    ]

    summary = state.get_index_summary(now=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc))

    assert summary.total_grants == 2
    assert summary.programme_count == 2
    assert summary.total_budget_eur == 2_000_000
    assert summary.total_budget_display == "EUR 2.0M"
    assert summary.closest_deadline == "2026-07-20"
    assert summary.closest_deadline_days == 3


def test_snapshot_round_trip_preserves_source_language(tmp_path):
    snapshot_path = tmp_path / "grant-index.json"
    snapshot_store = IndexSnapshotStore(snapshot_path)
    grant = make_grant("TOPIC-BG")
    grant.source_language = "bg"

    snapshot_store.save(
        grants=[grant],
        embeddings={},
        status_payload={"phase": "ready", "message": "ready"},
    )

    envelope = snapshot_store.load()

    assert envelope is not None
    loaded = IndexSnapshotStore(snapshot_path).load()
    assert loaded is not None
    restored_grant = IndexSnapshotStore(snapshot_path)
    payload = restored_grant.load()
    assert payload is not None
    state_grant = payload.grants[0]
    assert state_grant["source_language"] == "bg"
