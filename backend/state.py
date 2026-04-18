from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock, Thread

import sentry_sdk

from .config import Settings
from .ec_client import ECSearchClient
from .embeddings import EmbeddingService, build_grant_embeddings
from .indexer import CALL_PREFIXES, build_grant_index
from .models import GrantRecord, IndexBuildProgress, IndexStatus, IndexSummary
from .observability import capture_backend_exception
from .snapshot_store import IndexSnapshotStore, grant_from_snapshot_payload

logger = logging.getLogger(__name__)


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(reason for reason in reasons if reason))


def _format_budget_eur(value: int) -> str:
    if value >= 1_000_000:
        return f"EUR {value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"EUR {value / 1_000:.1f}K"
    return f"EUR {value}"


def _snapshot_written_at(snapshot) -> datetime:
    try:
        return datetime.fromisoformat(snapshot.written_at)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


class AppState:
    def __init__(
        self,
        *,
        settings: Settings,
        client: ECSearchClient | None = None,
        embedding_service: EmbeddingService | None = None,
        prefixes: list[str] | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or ECSearchClient(
            timeout_seconds=settings.ec_timeout_seconds,
            max_retries=settings.ec_max_retries,
            retry_backoff_seconds=settings.ec_retry_backoff_seconds,
        )
        self.embedding_service = embedding_service
        self.prefixes = prefixes or list(CALL_PREFIXES)
        self.snapshot_store = IndexSnapshotStore(settings.index_snapshot_path)
        self.seed_snapshot_store = IndexSnapshotStore(settings.index_seed_snapshot_path)
        self._lock = Lock()
        self._thread: Thread | None = None
        self._grants: list[GrantRecord] = []
        self._grant_embeddings: dict[str, list[float]] = {}
        self._snapshot_loaded = False
        self._snapshot_source: str | None = None
        self._snapshot_written_at: datetime | None = None
        self._indexing_started_once = False
        self._status = IndexStatus(
            phase="idle",
            message="Index not started",
            total_prefixes=len(self.prefixes),
            coverage_complete=False,
            matching_available=False,
        )
        self._load_snapshot()

    def _load_snapshot(self) -> None:
        runtime_snapshot = self.snapshot_store.load()
        seed_snapshot = self.seed_snapshot_store.load()
        candidates: list[tuple[str, object]] = []
        if runtime_snapshot is not None:
            candidates.append(("runtime", runtime_snapshot))
        if seed_snapshot is not None:
            candidates.append(("bundled", seed_snapshot))

        for source, snapshot in sorted(
            candidates,
            key=lambda candidate: (
                len(candidate[1].grants),
                _snapshot_written_at(candidate[1]),
                candidate[0] == "runtime",
            ),
            reverse=True,
        ):
            if self._apply_snapshot(snapshot, source=source):
                return

        if seed_snapshot is not None and self._apply_snapshot(seed_snapshot, source="bundled"):
            return

    def _apply_snapshot(self, snapshot, *, source: str) -> bool:
        grants = [grant_from_snapshot_payload(payload) for payload in snapshot.grants]
        if not grants:
            return False
        try:
            written_at = datetime.fromisoformat(snapshot.written_at)
        except ValueError:
            written_at = datetime.now(timezone.utc)

        status_payload = dict(snapshot.status_payload)
        base_status = IndexStatus.model_validate(status_payload)
        reasons = [*base_status.degradation_reasons, "stale_snapshot_mode"]
        if source == "bundled":
            reasons.append("bundled_seed_mode")
        reasons = _dedupe_reasons(reasons)

        self._grants = grants
        self._grant_embeddings = dict(snapshot.embeddings)
        self._snapshot_loaded = True
        self._snapshot_source = source
        self._snapshot_written_at = written_at
        self._status = IndexStatus(
            phase="ready_degraded",
            message="Using bundled seed snapshot while live refresh runs"
            if source == "bundled"
            else "Using saved index while live refresh runs",
            indexed_grants=len(grants),
            scanned_prefixes=0,
            total_prefixes=len(self.prefixes),
            failed_prefixes=0,
            truncated_prefixes=0,
            embeddings_ready=base_status.embeddings_ready,
            degraded=True,
            coverage_complete=False,
            matching_available=True,
            degradation_reasons=reasons,
            started_at=None,
            finished_at=written_at.isoformat(),
            snapshot_loaded=True,
            snapshot_source=source,
            snapshot_age_seconds=self._snapshot_age_seconds(reference_time=datetime.now(timezone.utc)),
            refresh_in_progress=False,
        )
        return True

    def ensure_indexing_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._indexing_started_once:
                return
            if (
                not self._snapshot_loaded
                and self._status.phase in {"ready", "ready_degraded"}
                and not self._status.refresh_in_progress
            ):
                return

            started_at = datetime.now(timezone.utc).isoformat()
            if self._snapshot_loaded and self._grants:
                snapshot_reason = "bundled_seed_mode" if self._snapshot_source == "bundled" else "stale_snapshot_mode"
                self._status = self._status.model_copy(
                    update={
                        "phase": "ready_degraded",
                        "message": "Using bundled seed snapshot while live refresh runs"
                        if self._snapshot_source == "bundled"
                        else "Using saved index while live refresh runs",
                        "degraded": True,
                        "matching_available": True,
                        "coverage_complete": False,
                        "degradation_reasons": _dedupe_reasons(
                            [*self._status.degradation_reasons, snapshot_reason]
                        ),
                        "started_at": started_at,
                        "finished_at": self._status.finished_at,
                        "current_prefix": None,
                        "current_page": None,
                        "pages_fetched": 0,
                        "requests_completed": 0,
                        "last_progress_at": None,
                        "snapshot_loaded": True,
                        "snapshot_source": self._snapshot_source,
                        "snapshot_age_seconds": self._snapshot_age_seconds(),
                        "refresh_in_progress": True,
                        "refresh_indexed_grants": 0,
                    }
                )
            else:
                self._status = IndexStatus(
                    phase="building",
                    message="Indexing live grants",
                    indexed_grants=0,
                    scanned_prefixes=0,
                    total_prefixes=len(self.prefixes),
                    failed_prefixes=0,
                    truncated_prefixes=0,
                    embeddings_ready=False,
                    degraded=False,
                    coverage_complete=False,
                    matching_available=False,
                    degradation_reasons=[],
                    started_at=started_at,
                    current_prefix=None,
                    current_page=None,
                    pages_fetched=0,
                    requests_completed=0,
                    last_progress_at=None,
                    snapshot_loaded=False,
                    snapshot_source=None,
                    snapshot_age_seconds=None,
                    refresh_in_progress=True,
                    refresh_indexed_grants=0,
                )
            self._indexing_started_once = True
            self._thread = Thread(target=self._build_index, daemon=True)
            self._thread.start()

    def _build_index(self) -> None:
        started_at = self.get_status().started_at or datetime.now(timezone.utc).isoformat()
        try:
            grants, build_details = build_grant_index(
                client=self.client,
                prefixes=self.prefixes,
                page_size=self.settings.ec_page_size,
                max_pages_per_prefix=self.settings.ec_max_pages_per_prefix,
                progress_callback=self._update_progress,
            )
            grant_embeddings: dict[str, list[float]] = {}
            embeddings_ready = False
            degradation_reasons = list(build_details.degradation_reasons)

            if self.embedding_service is not None and self.settings.openai_api_key:
                try:
                    with sentry_sdk.start_span(op="grant_index.embeddings", name="Build grant embeddings") as span:
                        span.set_data("grant_count", len(grants))
                        grant_embeddings = build_grant_embeddings(
                            grants,
                            embedding_service=self.embedding_service,
                        )
                        span.set_data("embedding_count", len(grant_embeddings))
                    embeddings_ready = bool(grant_embeddings)
                    sentry_sdk.set_measurement("index_embeddings_built", len(grant_embeddings))
                except Exception as exc:
                    capture_backend_exception(
                        exc,
                        component="indexer",
                        operation="build_grant_embeddings",
                        model=getattr(self.embedding_service, "model", None),
                        fallback_used=True,
                        context={
                            "grant_count": len(grants),
                        },
                    )
                    grant_embeddings = {}
                    embeddings_ready = False
                    if "embedding_build_failed" not in degradation_reasons:
                        degradation_reasons.append("embedding_build_failed")
                    logger.exception("Grant embedding build failed")
            else:
                if "lexical_only_mode" not in degradation_reasons:
                    degradation_reasons.append("lexical_only_mode")

            finished_at = datetime.now(timezone.utc)
            degradation_reasons = _dedupe_reasons(degradation_reasons)
            if self._snapshot_loaded and self._grants and not grants and build_details.failed_prefixes > 0:
                with self._lock:
                    snapshot_reason = "bundled_seed_mode" if self._snapshot_source == "bundled" else "stale_snapshot_mode"
                    reasons = _dedupe_reasons(
                        [*self._status.degradation_reasons, *degradation_reasons, snapshot_reason]
                    )
                    self._status = self._status.model_copy(
                        update={
                            "phase": "ready_degraded",
                            "message": "Using bundled seed snapshot while live refresh returned no usable data"
                            if self._snapshot_source == "bundled"
                            else "Using saved index while live refresh returned no usable data",
                            "degraded": True,
                            "matching_available": True,
                            "failed_prefixes": build_details.failed_prefixes,
                            "truncated_prefixes": build_details.truncated_prefixes,
                            "degradation_reasons": reasons,
                            "finished_at": finished_at.isoformat(),
                            "snapshot_source": self._snapshot_source,
                            "refresh_in_progress": False,
                        }
                    )
                return
            degraded = bool(degradation_reasons)
            fresh_status = IndexStatus(
                phase="ready_degraded" if degraded else "ready",
                message="Index ready with degraded coverage or matching quality" if degraded else "Index ready",
                indexed_grants=len(grants),
                scanned_prefixes=len(self.prefixes),
                total_prefixes=len(self.prefixes),
                failed_prefixes=build_details.failed_prefixes,
                truncated_prefixes=build_details.truncated_prefixes,
                embeddings_ready=embeddings_ready,
                degraded=degraded,
                coverage_complete=build_details.failed_prefixes == 0 and build_details.truncated_prefixes == 0,
                matching_available=True,
                degradation_reasons=degradation_reasons,
                started_at=started_at,
                finished_at=finished_at.isoformat(),
                current_prefix=None,
                current_page=None,
                pages_fetched=0,
                requests_completed=0,
                last_progress_at=finished_at.isoformat(),
                snapshot_loaded=False,
                snapshot_source=None,
                snapshot_age_seconds=None,
                refresh_in_progress=False,
                refresh_indexed_grants=len(grants),
            )
            with self._lock:
                self._grants = grants
                self._grant_embeddings = grant_embeddings
                self._snapshot_loaded = False
                self._snapshot_source = None
                self._snapshot_written_at = finished_at
                self._status = fresh_status
            self.snapshot_store.save(
                grants=grants,
                embeddings=grant_embeddings,
                status_payload=fresh_status.model_dump(),
                written_at=finished_at,
            )
        except Exception as exc:
            capture_backend_exception(
                exc,
                component="indexer",
                operation="build_grant_index",
                fallback_used=False,
                context={
                    "scanned_prefixes": self._status.scanned_prefixes,
                    "failed_prefixes": self._status.failed_prefixes,
                },
            )
            finished_at = datetime.now(timezone.utc).isoformat()
            with self._lock:
                if self._snapshot_loaded and self._grants:
                    snapshot_reason = "bundled_seed_mode" if self._snapshot_source == "bundled" else "stale_snapshot_mode"
                    reasons = _dedupe_reasons(
                        [*self._status.degradation_reasons, snapshot_reason, "index_build_failed"]
                    )
                    self._status = self._status.model_copy(
                        update={
                            "phase": "ready_degraded",
                            "message": "Using bundled seed snapshot while live refresh failed"
                            if self._snapshot_source == "bundled"
                            else "Using saved index while live refresh failed",
                            "degraded": True,
                            "matching_available": True,
                            "degradation_reasons": reasons,
                            "finished_at": finished_at,
                            "snapshot_source": self._snapshot_source,
                            "refresh_in_progress": False,
                        }
                    )
                else:
                    self._status = IndexStatus(
                        phase="error",
                        message=f"Indexing failed: {exc}",
                        indexed_grants=0,
                        scanned_prefixes=self._status.scanned_prefixes,
                        total_prefixes=len(self.prefixes),
                        failed_prefixes=max(1, self._status.failed_prefixes),
                        truncated_prefixes=self._status.truncated_prefixes,
                        embeddings_ready=False,
                        degraded=True,
                        coverage_complete=False,
                        matching_available=False,
                        degradation_reasons=["index_build_failed"],
                        started_at=started_at,
                        finished_at=finished_at,
                        current_prefix=self._status.current_prefix,
                        current_page=self._status.current_page,
                        pages_fetched=self._status.pages_fetched,
                        requests_completed=self._status.requests_completed,
                        last_progress_at=self._status.last_progress_at,
                        snapshot_loaded=False,
                        snapshot_source=None,
                        snapshot_age_seconds=None,
                        refresh_in_progress=False,
                        refresh_indexed_grants=self._status.refresh_indexed_grants,
                    )
            logger.exception("Grant index build failed")

    def _update_progress(self, progress: IndexBuildProgress) -> None:
        with self._lock:
            if self._snapshot_loaded and self._grants:
                phase = "ready_degraded"
                message = (
                    "Using bundled seed snapshot while live refresh runs"
                    if self._snapshot_source == "bundled"
                    else "Using saved index while live refresh runs"
                )
                matching_available = True
                indexed_grants = len(self._grants)
                degraded = True
                snapshot_reason = "bundled_seed_mode" if self._snapshot_source == "bundled" else "stale_snapshot_mode"
                reasons = _dedupe_reasons([*self._status.degradation_reasons, snapshot_reason])
                embeddings_ready = self._status.embeddings_ready
            else:
                phase = "building"
                message = "Indexing live grants"
                matching_available = False
                indexed_grants = 0
                degraded = progress.failed_prefixes > 0
                reasons = ["prefix_fetch_failed"] if progress.failed_prefixes > 0 else []
                embeddings_ready = False

            self._status = self._status.model_copy(
                update={
                    "phase": phase,
                    "message": message,
                    "indexed_grants": indexed_grants,
                    "scanned_prefixes": progress.scanned_prefixes,
                    "total_prefixes": progress.total_prefixes,
                    "failed_prefixes": progress.failed_prefixes,
                    "degraded": degraded,
                    "coverage_complete": False,
                    "matching_available": matching_available,
                    "degradation_reasons": reasons,
                    "current_prefix": progress.current_prefix,
                    "current_page": progress.current_page,
                    "pages_fetched": progress.pages_fetched,
                    "requests_completed": progress.requests_completed,
                    "last_progress_at": progress.last_progress_at,
                    "refresh_in_progress": True,
                    "refresh_indexed_grants": progress.indexed_grants,
                    "snapshot_loaded": self._snapshot_loaded,
                    "snapshot_source": self._snapshot_source,
                    "snapshot_age_seconds": self._snapshot_age_seconds()
                    if self._snapshot_loaded
                    else None,
                    "embeddings_ready": embeddings_ready,
                }
            )

    def _snapshot_age_seconds(self, reference_time: datetime | None = None) -> int | None:
        if self._snapshot_written_at is None:
            return None
        now = reference_time or datetime.now(timezone.utc)
        return max(0, int((now - self._snapshot_written_at).total_seconds()))

    def get_status(self) -> IndexStatus:
        with self._lock:
            status = self._status.model_copy(deep=True)
            if status.snapshot_loaded:
                status.snapshot_age_seconds = self._snapshot_age_seconds()
                status.snapshot_source = self._snapshot_source
            else:
                status.snapshot_source = None
            if status.refresh_in_progress and status.last_progress_at is not None:
                try:
                    last_progress = datetime.fromisoformat(status.last_progress_at)
                except ValueError:
                    return status
                stall_seconds = int((datetime.now(timezone.utc) - last_progress).total_seconds())
                if stall_seconds >= self.settings.index_refresh_stall_seconds:
                    status.degraded = True
                    status.phase = "ready_degraded" if status.matching_available else status.phase
                    status.message = "Using saved index while live refresh is delayed"
                    status.degradation_reasons = _dedupe_reasons(
                        [*status.degradation_reasons, "refresh_delayed"]
                    )
        status.summary = self.get_index_summary()
        return status

    def get_grants(self) -> list[GrantRecord]:
        with self._lock:
            return list(self._grants)

    def get_grant_embeddings(self) -> dict[str, list[float]]:
        with self._lock:
            return dict(self._grant_embeddings)

    def get_index_summary(self, now: datetime | None = None) -> IndexSummary:
        with self._lock:
            grants = list(self._grants)

        reference_time = now or datetime.now(timezone.utc)
        programme_count = len(
            {
                grant.framework_programme
                for grant in grants
                if grant.framework_programme
            }
        )
        total_budget_eur = sum(
            grant.budget_amount_eur
            for grant in grants
            if isinstance(grant.budget_amount_eur, int)
        )
        closest = min(
            (
                grant
                for grant in grants
                if grant.deadline_at is not None and grant.deadline_at >= reference_time
            ),
            key=lambda grant: grant.deadline_at,
            default=None,
        )
        return IndexSummary(
            total_grants=len(grants),
            programme_count=programme_count,
            total_budget_eur=total_budget_eur,
            total_budget_display=_format_budget_eur(total_budget_eur) if total_budget_eur else None,
            closest_deadline=closest.deadline if closest is not None else None,
            closest_deadline_days=closest.days_left(now=reference_time) if closest is not None else None,
        )
