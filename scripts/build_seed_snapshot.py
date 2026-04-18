from __future__ import annotations

import argparse
from datetime import datetime, timezone

from backend.config import load_settings
from backend.ec_client import ECSearchClient
from backend.indexer import CALL_PREFIXES, filter_indexable_grants
from backend.normalize import normalize_grant
from backend.snapshot_store import IndexSnapshotStore

SUPPLEMENTAL_QUERY_STREAMS = [
    "2026",
    "2027",
    "forthcoming",
    "AGRIP-SIMPLE-2026",
    "AGRIP-MULTI-2026",
    "EP-LINC-SUBV-2026",
    "MSCA-2026",
    "MSCA-2027",
    "HORIZON-MSCA-2026",
    "HORIZON-MSCA-2027",
    "RFCS-2026",
    "SMP-CONS-2026",
    "PPPA-2026",
    "EIT-2026",
    "EIT-2027",
    "HORIZON-EIT-2025",
    "HORIZON-NEB-2026",
    "HORIZON-NEB-2027",
    "DIGITAL-2022",
    "DIGITAL-2023",
    "DIGITAL-2024",
]


def dedupe_grants(grants):
    best_by_id = {}
    order = []
    for grant in grants:
        if not grant.id or grant.id in best_by_id:
            continue
        best_by_id[grant.id] = grant
        order.append(grant.id)
    return [best_by_id[grant_id] for grant_id in order]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a bundled seed snapshot with breadth-first EC prefix crawling.",
    )
    parser.add_argument(
        "--target-grants",
        type=int,
        default=1000,
        help="Stop once at least this many usable grants have been collected.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="EC API page size.",
    )
    parser.add_argument(
        "--min-active-grants",
        type=int,
        default=300,
        help="Do not write the snapshot until at least this many active grants are included.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional output path. Defaults to INDEX_SEED_SNAPSHOT_PATH.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    output_path = args.output or settings.index_seed_snapshot_path
    client = ECSearchClient(
        timeout_seconds=settings.ec_timeout_seconds,
        max_retries=settings.ec_max_retries,
        retry_backoff_seconds=settings.ec_retry_backoff_seconds,
    )
    snapshot_store = IndexSnapshotStore(output_path)

    collected = []
    active_queries = list(dict.fromkeys([*CALL_PREFIXES, *SUPPLEMENTAL_QUERY_STREAMS]))
    now = datetime.now(timezone.utc)
    round_number = 1
    failed_prefixes = 0
    requests_completed = 0

    while active_queries:
        next_round_queries: list[str] = []

        for query in active_queries:
            try:
                payload = client.search(text=query, page_number=round_number, page_size=args.page_size)
            except Exception:
                failed_prefixes += 1
                continue

            requests_completed += 1
            results = payload.get("results", [])
            total_results = payload.get("totalResults")

            if isinstance(results, list):
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    metadata = item.get("metadata", {})
                    if not isinstance(metadata, dict):
                        continue
                    collected.append(normalize_grant(metadata, result_url=item.get("url")))

            if isinstance(total_results, int) and total_results > round_number * args.page_size:
                next_round_queries.append(query)
            elif isinstance(results, list) and len(results) == args.page_size:
                next_round_queries.append(query)

        filtered = filter_indexable_grants(collected, now=now)
        deduped = dedupe_grants(collected)
        programme_count = len({grant.framework_programme for grant in filtered if grant.framework_programme})
        print(
            f"round={round_number} raw={len(collected)} deduped={len(deduped)} filtered={len(filtered)} "
            f"programmes={programme_count} requests={requests_completed}",
            flush=True,
        )

        if len(deduped) >= args.target_grants and len(filtered) >= args.min_active_grants:
            active_ids = {grant.id for grant in filtered}
            inactive = [grant for grant in deduped if grant.id not in active_ids]
            snapshot_grants = [*filtered]
            remaining = max(0, args.target_grants - len(snapshot_grants))
            snapshot_grants.extend(inactive[:remaining])
            status_payload = {
                "phase": "ready_degraded",
                "message": (
                    f"Seed snapshot generated with {len(snapshot_grants)} records "
                    f"including {len(filtered)} active grants"
                ),
                "indexed_grants": len(snapshot_grants),
                "scanned_prefixes": len(CALL_PREFIXES),
                "total_prefixes": len(CALL_PREFIXES),
                "failed_prefixes": failed_prefixes,
                "truncated_prefixes": len(next_round_queries),
                "embeddings_ready": False,
                "degraded": True,
                "coverage_complete": False,
                "matching_available": True,
                "degradation_reasons": ["crawl_truncated", "lexical_only_mode"],
                "snapshot_loaded": False,
                "snapshot_source": None,
                "snapshot_age_seconds": None,
                "refresh_in_progress": False,
                "refresh_indexed_grants": 0,
            }
            snapshot_store.save(
                grants=snapshot_grants,
                embeddings={},
                status_payload=status_payload,
                written_at=datetime.now(timezone.utc),
            )
            print(
                f"saved {len(snapshot_grants)} grants to {output_path} "
                f"({len(filtered)} active, {len(snapshot_grants) - len(filtered)} additional records)",
                flush=True,
            )
            return 0

        active_queries = next_round_queries
        round_number += 1

    filtered = filter_indexable_grants(collected, now=now)
    deduped = dedupe_grants(collected)
    status_payload = {
        "phase": "ready_degraded",
        "message": f"Seed snapshot generated with {len(deduped)} records including {len(filtered)} active grants",
        "indexed_grants": len(deduped),
        "scanned_prefixes": len(CALL_PREFIXES),
        "total_prefixes": len(CALL_PREFIXES),
        "failed_prefixes": failed_prefixes,
        "truncated_prefixes": 0,
        "embeddings_ready": False,
        "degraded": True,
        "coverage_complete": True,
        "matching_available": True,
        "degradation_reasons": ["lexical_only_mode"] if failed_prefixes == 0 else ["lexical_only_mode", "prefix_fetch_failed"],
        "snapshot_loaded": False,
        "snapshot_source": None,
        "snapshot_age_seconds": None,
        "refresh_in_progress": False,
        "refresh_indexed_grants": 0,
    }
    snapshot_store.save(
        grants=deduped,
        embeddings={},
        status_payload=status_payload,
        written_at=datetime.now(timezone.utc),
    )
    print(f"saved {len(deduped)} grants to {output_path} ({len(filtered)} active grants)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
