from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock, Thread

import sentry_sdk

from .config import Settings
from .ec_client import ECSearchClient
from .embeddings import EmbeddingService, build_grant_embeddings
from .indexer import CALL_PREFIXES, build_grant_index
from .models import GrantRecord, IndexStatus

logger = logging.getLogger(__name__)


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
        self._lock = Lock()
        self._thread: Thread | None = None
        self._grants: list[GrantRecord] = []
        self._grant_embeddings: dict[str, list[float]] = {}
        self._status = IndexStatus(
            phase="idle",
            message="Index not started",
            total_prefixes=len(self.prefixes),
            coverage_complete=False,
            matching_available=False,
        )

    def ensure_indexing_started(self) -> None:
        with self._lock:
            if self._status.phase in {"ready", "ready_degraded"}:
                return
            if self._thread is not None and self._thread.is_alive():
                return

            started_at = datetime.now(timezone.utc).isoformat()
            self._status = IndexStatus(
                phase="building",
                message="Indexing live grants",
                indexed_grants=len(self._grants),
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
            )
            self._thread = Thread(target=self._build_index, daemon=True)
            self._thread.start()

    def _build_index(self) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
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
                    grant_embeddings = build_grant_embeddings(
                        grants,
                        embedding_service=self.embedding_service,
                    )
                    embeddings_ready = bool(grant_embeddings)
                except Exception as exc:
                    grant_embeddings = {}
                    embeddings_ready = False
                    if "embedding_build_failed" not in degradation_reasons:
                        degradation_reasons.append("embedding_build_failed")
                    logger.exception("Grant embedding build failed")
                    sentry_sdk.capture_exception(exc)
            else:
                if "lexical_only_mode" not in degradation_reasons:
                    degradation_reasons.append("lexical_only_mode")

            finished_at = datetime.now(timezone.utc).isoformat()
            degraded = bool(degradation_reasons)
            with self._lock:
                self._grants = grants
                self._grant_embeddings = grant_embeddings
                self._status = IndexStatus(
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
                    finished_at=finished_at,
                )
        except Exception as exc:
            finished_at = datetime.now(timezone.utc).isoformat()
            with self._lock:
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
                )
            logger.exception("Grant index build failed")
            sentry_sdk.capture_exception(exc)

    def _update_progress(
        self,
        scanned_prefixes: int,
        total_prefixes: int,
        failed_prefixes: int,
        indexed_grants: int,
    ) -> None:
        with self._lock:
            self._status = IndexStatus(
                phase="building",
                message="Indexing live grants",
                indexed_grants=indexed_grants,
                scanned_prefixes=scanned_prefixes,
                total_prefixes=total_prefixes,
                failed_prefixes=failed_prefixes,
                truncated_prefixes=self._status.truncated_prefixes,
                embeddings_ready=False,
                degraded=failed_prefixes > 0,
                coverage_complete=False,
                matching_available=False,
                degradation_reasons=["prefix_fetch_failed"] if failed_prefixes > 0 else [],
                started_at=self._status.started_at,
                finished_at=None,
            )

    def get_status(self) -> IndexStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def get_grants(self) -> list[GrantRecord]:
        with self._lock:
            return list(self._grants)

    def get_grant_embeddings(self) -> dict[str, list[float]]:
        with self._lock:
            return dict(self._grant_embeddings)
