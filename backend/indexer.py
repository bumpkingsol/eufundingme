from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import sentry_sdk

from .ec_client import ECSearchClient
from .models import GrantRecord, IndexBuildDetails, IndexBuildProgress
from .normalize import is_code_like_label, is_numericish, normalize_grant

logger = logging.getLogger(__name__)

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
    best_by_id: dict[str, GrantRecord] = {}
    order: list[str] = []

    for grant in grants:
        if not grant.id:
            continue
        if grant.status not in {"Open", "Forthcoming"}:
            continue
        if grant.deadline_at is not None and grant.deadline_at < reference_time:
            continue
        existing = best_by_id.get(grant.id)
        if existing is None:
            best_by_id[grant.id] = grant
            order.append(grant.id)
            continue
        if grant_quality_score(grant) > grant_quality_score(existing):
            best_by_id[grant.id] = grant

    return [best_by_id[grant_id] for grant_id in order]


def grant_quality_score(grant: GrantRecord) -> int:
    score = 0
    if grant.framework_programme and not is_numericish(grant.framework_programme):
        score += 3
    if grant.programme_division and not is_numericish(grant.programme_division):
        score += 2
    if "topic-details" in grant.portal_url:
        score += 1
    score += sum(1 for keyword in grant.keywords if not is_code_like_label(keyword))
    return score


def build_grant_index(
    *,
    client: ECSearchClient,
    prefixes: Sequence[str] | None = None,
    now: datetime | None = None,
    page_size: int = 100,
    max_pages_per_prefix: int | None = None,
    progress_callback: Callable[[IndexBuildProgress], None] | None = None,
) -> tuple[list[GrantRecord], IndexBuildDetails]:
    started_at = time.perf_counter()
    active_prefixes = list(prefixes or CALL_PREFIXES)
    collected: list[GrantRecord] = []
    failed_prefixes = 0
    truncated_prefixes = 0
    reference_time = now or datetime.now(timezone.utc)
    degradation_reasons: list[str] = []
    pages_fetched = 0
    requests_completed = 0

    for prefix_index, prefix in enumerate(active_prefixes, start=1):
        page_number = 1
        with sentry_sdk.start_span(op="grant_index.prefix", name=f"Crawl {prefix}") as span:
            span.set_data("prefix", prefix)
            span.set_data("page_size", page_size)
            span.set_data("max_pages_per_prefix", max_pages_per_prefix)
            try:
                while True:
                    if max_pages_per_prefix is not None and page_number > max_pages_per_prefix:
                        truncated_prefixes += 1
                        if "crawl_truncated" not in degradation_reasons:
                            degradation_reasons.append("crawl_truncated")
                        logger.warning("Grant crawl truncated by configured page cap", extra={"prefix": prefix})
                        sentry_sdk.add_breadcrumb(
                            category="grant_index",
                            message="Grant crawl truncated by configured page cap",
                            level="warning",
                            data={"prefix": prefix, "max_pages_per_prefix": max_pages_per_prefix},
                        )
                        break
                    payload = client.search(text=prefix, page_number=page_number, page_size=page_size)
                    requests_completed += 1
                    raw_results = payload.get("results", [])
                    if not isinstance(raw_results, list) or not raw_results:
                        break
                    pages_fetched += 1
                    for item in raw_results:
                        if not isinstance(item, dict):
                            continue
                        metadata = item.get("metadata", {})
                        if not isinstance(metadata, dict):
                            continue
                        collected.append(normalize_grant(metadata, result_url=item.get("url")))
                    if progress_callback is not None:
                        indexed_count = len(filter_indexable_grants(collected, now=reference_time))
                        progress_callback(
                            IndexBuildProgress(
                                scanned_prefixes=prefix_index - 1,
                                total_prefixes=len(active_prefixes),
                                failed_prefixes=failed_prefixes,
                                indexed_grants=indexed_count,
                                current_prefix=prefix,
                                current_page=page_number,
                                pages_fetched=pages_fetched,
                                requests_completed=requests_completed,
                                last_progress_at=datetime.now(timezone.utc).isoformat(),
                            )
                        )
                    total_results = payload.get("totalResults")
                    if isinstance(total_results, int) and total_results <= page_number * page_size:
                        break
                    if len(raw_results) < page_size:
                        break
                    page_number += 1
            except Exception:
                failed_prefixes += 1
                if "prefix_fetch_failed" not in degradation_reasons:
                    degradation_reasons.append("prefix_fetch_failed")
                logger.exception("Grant prefix crawl failed", extra={"prefix": prefix})
                sentry_sdk.capture_exception()
            finally:
                span.set_data("pages_fetched_total", pages_fetched)
                span.set_data("requests_completed_total", requests_completed)
                if progress_callback is not None:
                    indexed_count = len(filter_indexable_grants(collected, now=reference_time))
                    progress_callback(
                        IndexBuildProgress(
                            scanned_prefixes=prefix_index,
                            total_prefixes=len(active_prefixes),
                            failed_prefixes=failed_prefixes,
                            indexed_grants=indexed_count,
                            current_prefix=prefix,
                            current_page=page_number,
                            pages_fetched=pages_fetched,
                            requests_completed=requests_completed,
                            last_progress_at=datetime.now(timezone.utc).isoformat(),
                        )
                    )

    filtered_grants = filter_indexable_grants(collected, now=reference_time)
    sentry_sdk.set_measurement("index_requests_completed", requests_completed)
    sentry_sdk.set_measurement("index_pages_fetched", pages_fetched)
    sentry_sdk.set_measurement("index_indexed_grants", len(filtered_grants))
    sentry_sdk.set_measurement("index_failed_prefixes", failed_prefixes)
    sentry_sdk.set_measurement("index_truncated_prefixes", truncated_prefixes)
    sentry_sdk.set_measurement(
        "index_refresh_duration_ms",
        round((time.perf_counter() - started_at) * 1000, 3),
    )
    return (
        filtered_grants,
        IndexBuildDetails(
            failed_prefixes=failed_prefixes,
            truncated_prefixes=truncated_prefixes,
            degradation_reasons=degradation_reasons,
        ),
    )
