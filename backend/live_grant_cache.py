from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import GrantRecord


@dataclass(slots=True)
class CachedLiveGrantContext:
    stored_at: datetime
    grants_by_id: dict[str, GrantRecord]


class LiveGrantCache:
    def __init__(
        self,
        *,
        ttl_seconds: int = 30 * 60,
        max_contexts: int = 200,
    ) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_contexts = max_contexts
        self._contexts: OrderedDict[str, CachedLiveGrantContext] = OrderedDict()

    def store(self, request_id: str | None, grants: list[GrantRecord], *, now: datetime | None = None) -> None:
        if not request_id:
            return
        reference_time = now or datetime.now(timezone.utc)
        self._prune(reference_time)
        grants_by_id = {grant.id: grant for grant in grants if isinstance(grant, GrantRecord) and grant.id}
        if not grants_by_id:
            return
        self._contexts[request_id] = CachedLiveGrantContext(stored_at=reference_time, grants_by_id=grants_by_id)
        self._contexts.move_to_end(request_id)
        while len(self._contexts) > self.max_contexts:
            self._contexts.popitem(last=False)

    def get_grant(self, request_id: str | None, grant_id: str, *, now: datetime | None = None) -> GrantRecord | None:
        if not request_id:
            return None
        reference_time = now or datetime.now(timezone.utc)
        self._prune(reference_time)
        context = self._contexts.get(request_id)
        if context is None:
            return None
        self._contexts.move_to_end(request_id)
        return context.grants_by_id.get(grant_id)

    def _prune(self, reference_time: datetime) -> None:
        expired_before = reference_time - self.ttl
        stale_request_ids = [
            request_id
            for request_id, context in self._contexts.items()
            if context.stored_at < expired_before
        ]
        for request_id in stale_request_ids:
            self._contexts.pop(request_id, None)
