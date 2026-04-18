from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import scripts.build_seed_snapshot as build_seed_snapshot

from backend.config import Settings
from backend.models import GrantRecord
from backend.snapshot_store import IndexSnapshotStore


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
        search_text="ai grant",
    )


class FakeECSearchClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def search(self, *, text: str, page_number: int, page_size: int) -> dict[str, object]:
        assert text == "AI-2026"
        assert page_number == 1
        return {
            "results": [
                {
                    "metadata": {"id": "AI-2026-TOPIC-1"},
                    "url": "https://example.com/topic",
                }
            ],
            "totalResults": 1,
        }


def make_settings(output_path: Path, *, openai_api_key: str | None) -> Settings:
    return Settings(
        openai_api_key=openai_api_key,
        openai_embedding_model="text-embedding-3-large",
        index_seed_snapshot_path=str(output_path),
    )


def test_build_seed_snapshot_writes_lexical_only_seed_when_flag_absent(monkeypatch, tmp_path):
    output_path = tmp_path / "grant-index.seed.json"

    monkeypatch.setattr(
        build_seed_snapshot,
        "parse_args",
        lambda: SimpleNamespace(
            target_grants=1,
            page_size=100,
            min_active_grants=1,
            output="",
            with_embeddings=False,
        ),
    )
    monkeypatch.setattr(
        build_seed_snapshot,
        "load_settings",
        lambda: make_settings(output_path, openai_api_key="test-key"),
    )
    monkeypatch.setattr(build_seed_snapshot, "CALL_PREFIXES", ["AI-2026"])
    monkeypatch.setattr(build_seed_snapshot, "SUPPLEMENTAL_QUERY_STREAMS", [])
    monkeypatch.setattr(build_seed_snapshot, "ECSearchClient", FakeECSearchClient)
    monkeypatch.setattr(build_seed_snapshot, "normalize_grant", lambda metadata, result_url=None: make_grant("TOPIC-1"))
    monkeypatch.setattr(
        build_seed_snapshot,
        "build_grant_embeddings",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected embedding build")),
    )

    exit_code = build_seed_snapshot.main()

    snapshot = IndexSnapshotStore(output_path).load()
    assert exit_code == 0
    assert snapshot is not None
    assert snapshot.embeddings == {}
    assert snapshot.status_payload["embeddings_ready"] is False
    assert "lexical_only_mode" in snapshot.status_payload["degradation_reasons"]


def test_build_seed_snapshot_writes_embeddings_when_requested(monkeypatch, tmp_path):
    output_path = tmp_path / "grant-index.seed.json"

    monkeypatch.setattr(
        build_seed_snapshot,
        "parse_args",
        lambda: SimpleNamespace(
            target_grants=1,
            page_size=100,
            min_active_grants=1,
            output="",
            with_embeddings=True,
        ),
    )
    monkeypatch.setattr(
        build_seed_snapshot,
        "load_settings",
        lambda: make_settings(output_path, openai_api_key="test-key"),
    )
    monkeypatch.setattr(build_seed_snapshot, "CALL_PREFIXES", ["AI-2026"])
    monkeypatch.setattr(build_seed_snapshot, "SUPPLEMENTAL_QUERY_STREAMS", [])
    monkeypatch.setattr(build_seed_snapshot, "ECSearchClient", FakeECSearchClient)
    monkeypatch.setattr(build_seed_snapshot, "normalize_grant", lambda metadata, result_url=None: make_grant("TOPIC-1"))
    monkeypatch.setattr(
        build_seed_snapshot,
        "build_grant_embeddings",
        lambda grants, *, embedding_service: {"TOPIC-1": [0.1, 0.2, 0.3]},
    )

    exit_code = build_seed_snapshot.main()

    snapshot = IndexSnapshotStore(output_path).load()
    assert exit_code == 0
    assert snapshot is not None
    assert snapshot.embeddings == {"TOPIC-1": [0.1, 0.2, 0.3]}
    assert snapshot.status_payload["embeddings_ready"] is True
    assert "lexical_only_mode" not in snapshot.status_payload["degradation_reasons"]


def test_build_seed_snapshot_fails_without_writing_when_embeddings_requested_and_build_fails(
    monkeypatch,
    tmp_path,
):
    output_path = tmp_path / "grant-index.seed.json"

    monkeypatch.setattr(
        build_seed_snapshot,
        "parse_args",
        lambda: SimpleNamespace(
            target_grants=1,
            page_size=100,
            min_active_grants=1,
            output="",
            with_embeddings=True,
        ),
    )
    monkeypatch.setattr(
        build_seed_snapshot,
        "load_settings",
        lambda: make_settings(output_path, openai_api_key="test-key"),
    )
    monkeypatch.setattr(build_seed_snapshot, "CALL_PREFIXES", ["AI-2026"])
    monkeypatch.setattr(build_seed_snapshot, "SUPPLEMENTAL_QUERY_STREAMS", [])
    monkeypatch.setattr(build_seed_snapshot, "ECSearchClient", FakeECSearchClient)
    monkeypatch.setattr(build_seed_snapshot, "normalize_grant", lambda metadata, result_url=None: make_grant("TOPIC-1"))
    monkeypatch.setattr(
        build_seed_snapshot,
        "build_grant_embeddings",
        lambda grants, *, embedding_service: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code = build_seed_snapshot.main()

    assert exit_code == 1
    assert not output_path.exists()
