from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from .ec_client import ECSearchClient
from .models import GrantRecord
from .normalize import normalize_grant

CALL_PREFIXES = [
    "HORIZON-CL1-2026",
    "HORIZON-CL1-2027",
    "HORIZON-CL2-2026",
    "HORIZON-CL2-2027",
    "HORIZON-CL3-2026",
    "HORIZON-CL3-2027",
    "HORIZON-CL4-2026",
    "HORIZON-CL4-2027",
    "HORIZON-CL5-2026",
    "HORIZON-CL5-2027",
    "HORIZON-CL6-2026",
    "HORIZON-CL6-2027",
    "HORIZON-HLTH-2026",
    "HORIZON-HLTH-2027",
    "HORIZON-EIE-2026",
    "HORIZON-EIE-2027",
    "HORIZON-WIDERA-2026",
    "HORIZON-WIDERA-2027",
    "HORIZON-INFRA-2026",
    "HORIZON-INFRA-2027",
    "HORIZON-MISS-2026",
    "HORIZON-MISS-2027",
    "HORIZON-JU-2026",
    "HORIZON-JU-2027",
    "HORIZON-EIC-2026",
    "HORIZON-EIC-2027",
    "DIGITAL-2026",
    "DIGITAL-2027",
    "ERASMUS-2026",
    "ERASMUS-2027",
    "CREA-2026",
    "CREA-2027",
    "CERV-2026",
    "CERV-2027",
    "SMP-COSME-2026",
    "SMP-COSME-2027",
    "EU4H-2026",
    "EU4H-2027",
    "LIFE-2026",
    "LIFE-2027",
    "CEF-2026",
    "CEF-2027",
    "EDF-2026",
    "EDF-2027",
    "ISF-2026",
    "ISF-2027",
]


def filter_indexable_grants(
    grants: Sequence[GrantRecord],
    *,
    now: datetime | None = None,
) -> list[GrantRecord]:
    reference_time = now or datetime.now(timezone.utc)
    seen_ids: set[str] = set()
    kept: list[GrantRecord] = []

    for grant in grants:
        if not grant.id or grant.id in seen_ids:
            continue
        if grant.status not in {"Open", "Forthcoming"}:
            continue
        if grant.deadline_at is not None and grant.deadline_at < reference_time:
            continue
        seen_ids.add(grant.id)
        kept.append(grant)

    return kept


def build_grant_index(
    *,
    client: ECSearchClient,
    prefixes: Sequence[str] | None = None,
    now: datetime | None = None,
    page_size: int = 100,
    max_pages_per_prefix: int = 1,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
) -> list[GrantRecord]:
    active_prefixes = list(prefixes or CALL_PREFIXES)
    collected: list[GrantRecord] = []
    failed_prefixes = 0
    reference_time = now or datetime.now(timezone.utc)

    for prefix_index, prefix in enumerate(active_prefixes, start=1):
        try:
            for page_number in range(1, max_pages_per_prefix + 1):
                payload = client.search(text=prefix, page_number=page_number, page_size=page_size)
                raw_results = payload.get("results", [])
                if not isinstance(raw_results, list) or not raw_results:
                    break
                for item in raw_results:
                    if not isinstance(item, dict):
                        continue
                    metadata = item.get("metadata", {})
                    if not isinstance(metadata, dict):
                        continue
                    collected.append(normalize_grant(metadata, result_url=item.get("url")))
                if len(raw_results) < page_size:
                    break
        except Exception:
            failed_prefixes += 1
        finally:
            if progress_callback is not None:
                indexed_count = len(filter_indexable_grants(collected, now=reference_time))
                progress_callback(prefix_index, len(active_prefixes), failed_prefixes, indexed_count)

    return filter_indexable_grants(collected, now=reference_time)
