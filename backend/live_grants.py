from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .ec_client import ECSearchClient
from .embeddings import expanded_informative_terms, tokenize_terms
from .indexer import filter_indexable_grants, grant_quality_score
from .models import GrantRecord
from .normalize import normalize_grant

DEFAULT_QUERY_LIMIT = 8
DEFAULT_PAGE_SIZE = 25
DEFAULT_PAGES_PER_QUERY = 1
DEFAULT_CANDIDATE_LIMIT = 60

HEALTH_TERMS = {"health", "healthcare", "patient", "patients", "telemedicine", "telehealth", "clinical"}
SECURITY_TERMS = {"security", "cybersecurity", "privacy", "protection", "cloud", "risk", "risks"}
CLIMATE_TERMS = {"battery", "batteries", "energy", "electric", "mobility", "recycling", "renewable"}


@dataclass(slots=True)
class LiveGrantRetrievalResult:
    grants: list[GrantRecord]
    queries: list[str] = field(default_factory=list)
    degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)
    source: str = "live_retrieval"


def _ordered_tokens(text: str) -> list[str]:
    return [token for token in text.lower().split() if token]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def generate_live_search_queries(company_description: str, *, limit: int = DEFAULT_QUERY_LIMIT) -> list[str]:
    raw_tokens = tokenize_terms(company_description)
    terms = expanded_informative_terms(company_description)
    normalized_text = company_description.lower()
    queries: list[str] = []

    def add(query: str) -> None:
        if query and query not in queries:
            queries.append(query)

    ai_present = {"artificial", "intelligence"} <= terms
    if ai_present:
        add("artificial intelligence")
        add("AI innovation")
    if ai_present and "safety" in terms:
        add("AI safety")
    if "foundation" in raw_tokens and ("model" in raw_tokens or "models" in raw_tokens):
        add("foundation models")
    if "llm" in raw_tokens or ("language" in raw_tokens and ("model" in raw_tokens or "models" in raw_tokens)):
        add("large language models")
    if "reasoning" in raw_tokens:
        add("reasoning AI")
    if "deployment" in terms and ai_present:
        add("AI deployment")
    if "robotics" in raw_tokens or "robotic" in raw_tokens:
        add("robotics")

    if HEALTH_TERMS & raw_tokens:
        add("digital health")
        add("health data")
    if "telemedicine" in raw_tokens or "telehealth" in raw_tokens:
        add("telemedicine")

    if SECURITY_TERMS & raw_tokens:
        add("cybersecurity")
    if "cloud" in raw_tokens and "security" in raw_tokens:
        add("cloud security")
    if "privacy" in raw_tokens or ("data" in raw_tokens and "protection" in raw_tokens):
        add("data protection")

    if CLIMATE_TERMS & raw_tokens:
        if "battery" in raw_tokens or "batteries" in raw_tokens:
            add("battery innovation")
        if "electric" in raw_tokens or "mobility" in raw_tokens:
            add("electric mobility")
        if "energy" in raw_tokens:
            add("energy storage")

    known_phrases = [
        "digital health",
        "health data",
        "telemedicine",
        "cloud security",
        "data protection",
        "energy storage",
        "electric mobility",
        "battery recycling",
    ]
    for phrase in known_phrases:
        if phrase in normalized_text:
            add(phrase)

    if len(queries) < limit:
        ordered = _ordered_tokens(company_description)
        top_terms = [term for term in ordered if term in terms]
        for index in range(len(top_terms) - 1):
            candidate = f"{top_terms[index]} {top_terms[index + 1]}"
            if len(tokenize_terms(candidate)) >= 2:
                add(candidate)
            if len(queries) >= limit:
                break

    if not queries:
        fallback_terms = list(expanded_informative_terms(company_description))[:3]
        if fallback_terms:
            add(" ".join(fallback_terms))

    return queries[:limit]


def _grant_relevance_score(company_description: str, grant: GrantRecord, query: str) -> int:
    company_terms = expanded_informative_terms(company_description)
    grant_text = " ".join(
        part
        for part in [
            grant.title,
            grant.framework_programme,
            grant.programme_division,
            " ".join(grant.keywords),
            grant.description,
            grant.search_text,
        ]
        if part
    )
    grant_terms = expanded_informative_terms(grant_text)
    query_terms = expanded_informative_terms(query)
    company_overlap = len(company_terms & grant_terms)
    query_overlap = len(query_terms & grant_terms)
    normalized_query = query.lower()
    direct_phrase = normalized_query in grant_text.lower()
    score = company_overlap * 3 + query_overlap * 4 + grant_quality_score(grant)
    if direct_phrase:
        score += 5
    if query_overlap == 0 and not direct_phrase:
        return 0
    if company_overlap < 2 and query_overlap < 2 and not direct_phrase:
        return 0
    return score


class LiveGrantService:
    def __init__(
        self,
        *,
        client: ECSearchClient,
        page_size: int = DEFAULT_PAGE_SIZE,
        pages_per_query: int = DEFAULT_PAGES_PER_QUERY,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        self.client = client
        self.page_size = page_size
        self.pages_per_query = pages_per_query
        self.candidate_limit = candidate_limit

    def retrieve(
        self,
        company_description: str,
        *,
        queries: list[str] | None = None,
        now: datetime | None = None,
    ) -> LiveGrantRetrievalResult:
        active_queries = queries or generate_live_search_queries(company_description)
        reference_time = now or datetime.now(timezone.utc)
        best_by_id: dict[str, tuple[int, GrantRecord]] = {}
        failed_queries = 0

        for query in active_queries:
            for page_number in range(1, self.pages_per_query + 1):
                try:
                    payload = self.client.search(text=query, page_number=page_number, page_size=self.page_size)
                except Exception:
                    failed_queries += 1
                    break
                raw_results = payload.get("results", [])
                if not isinstance(raw_results, list) or not raw_results:
                    break
                for item in raw_results:
                    if not isinstance(item, dict):
                        continue
                    metadata = item.get("metadata", {})
                    if not isinstance(metadata, dict):
                        continue
                    grant = normalize_grant(metadata, result_url=item.get("url"))
                    filtered = filter_indexable_grants([grant], now=reference_time)
                    if not filtered:
                        continue
                    grant = filtered[0]
                    score = _grant_relevance_score(company_description, grant, query)
                    if score <= 0:
                        continue
                    existing = best_by_id.get(grant.id)
                    if existing is None or score > existing[0]:
                        best_by_id[grant.id] = (score, grant)

        ranked = sorted(
            best_by_id.values(),
            key=lambda item: (-item[0], item[1].deadline or "9999-12-31", item[1].title),
        )
        grants = [grant for _, grant in ranked[: self.candidate_limit]]
        reasons: list[str] = []
        if failed_queries and grants:
            reasons.append("live_query_partial_failure")
        elif failed_queries and not grants:
            reasons.append("live_retrieval_failed")

        return LiveGrantRetrievalResult(
            grants=grants,
            queries=_dedupe(active_queries),
            degraded=bool(reasons),
            degradation_reasons=reasons,
            source="live_retrieval",
        )
