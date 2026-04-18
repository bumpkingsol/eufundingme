from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock, Thread

from .config import Settings
from .ec_client import ECSearchClient
from .embeddings import EmbeddingService, build_grant_embeddings
from .indexer import CALL_PREFIXES, build_grant_index
from .models import GrantRecord, IndexStatus


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
        self.client = client or ECSearchClient(timeout_seconds=settings.ec_timeout_seconds)
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
        )

    def ensure_indexing_started(self) -> None:
        with self._lock:
            if self._status.phase == "ready":
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
                embeddings_ready=False,
                started_at=started_at,
            )
            self._thread = Thread(target=self._build_index, daemon=True)
            self._thread.start()

    def _build_index(self) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        try:
            grants = build_grant_index(
                client=self.client,
                prefixes=self.prefixes,
                page_size=self.settings.ec_page_size,
                max_pages_per_prefix=self.settings.ec_max_pages_per_prefix,
                progress_callback=self._update_progress,
            )
            grant_embeddings: dict[str, list[float]] = {}
            embeddings_ready = False

            if self.embedding_service is not None and self.settings.openai_api_key:
                try:
                    grant_embeddings = build_grant_embeddings(
                        grants,
                        embedding_service=self.embedding_service,
                    )
                    embeddings_ready = bool(grant_embeddings)
                except Exception:
                    grant_embeddings = {}
                    embeddings_ready = False

            finished_at = datetime.now(timezone.utc).isoformat()
            with self._lock:
                self._grants = grants
                self._grant_embeddings = grant_embeddings
                self._status = IndexStatus(
                    phase="ready",
                    message="Index ready",
                    indexed_grants=len(grants),
                    scanned_prefixes=len(self.prefixes),
                    total_prefixes=len(self.prefixes),
                    failed_prefixes=self._status.failed_prefixes,
                    embeddings_ready=embeddings_ready,
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
                    embeddings_ready=False,
                    started_at=started_at,
                    finished_at=finished_at,
                )

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
                embeddings_ready=False,
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
