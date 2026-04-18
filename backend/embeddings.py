from __future__ import annotations

import math
import re
from collections.abc import Sequence

from openai import OpenAI

from .models import GrantRecord, MatchCandidate

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "to",
    "we",
    "with",
    "across",
}
LOW_SIGNAL_TERMS = {
    "build",
    "building",
    "business",
    "businesses",
    "company",
    "companies",
    "enterprise",
    "enterprises",
    "eu",
    "europe",
    "european",
    "government",
    "governments",
    "industry",
    "industries",
    "organisation",
    "organisations",
    "organization",
    "organizations",
    "programme",
    "programmes",
    "program",
    "programs",
    "sector",
    "sectors",
    "solution",
    "solutions",
}


class EmbeddingService:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=list(texts))
        return [item.embedding for item in response.data]


def cosine_similarity(lhs: Sequence[float], rhs: Sequence[float]) -> float:
    lhs_norm = math.sqrt(sum(value * value for value in lhs))
    rhs_norm = math.sqrt(sum(value * value for value in rhs))
    if lhs_norm == 0 or rhs_norm == 0:
        return 0.0
    dot = sum(left * right for left, right in zip(lhs, rhs, strict=False))
    return dot / (lhs_norm * rhs_norm)


def tokenize_terms(text: str) -> set[str]:
    return {match.group(0) for match in TOKEN_PATTERN.finditer(text.lower())}


def informative_terms(text: str) -> set[str]:
    return {
        term
        for term in tokenize_terms(text)
        if term not in STOPWORDS and term not in LOW_SIGNAL_TERMS
    }


def lexical_shortlist(
    company_description: str,
    grants: Sequence[GrantRecord],
    *,
    limit: int = 15,
) -> list[MatchCandidate]:
    query_terms = informative_terms(company_description)
    if not query_terms:
        return []
    scored: list[MatchCandidate] = []

    for grant in grants:
        haystack_terms = informative_terms(grant.search_text or grant.title)
        overlap = query_terms & haystack_terms
        if not overlap:
            continue
        shortlist_score = float(len(overlap))
        scored.append(MatchCandidate(grant=grant, shortlist_score=shortlist_score))

    scored.sort(
        key=lambda candidate: (
            -candidate.shortlist_score,
            candidate.grant.deadline or "9999-12-31",
            candidate.grant.title,
        )
    )
    return scored[:limit]


def embedding_shortlist(
    company_description: str,
    grants: Sequence[GrantRecord],
    *,
    grant_embeddings: dict[str, list[float]],
    embedding_service: EmbeddingService,
    limit: int = 15,
) -> list[MatchCandidate]:
    if not grants or not grant_embeddings:
        return lexical_shortlist(company_description, grants, limit=limit)

    company_vectors = embedding_service.embed_texts([company_description])
    if not company_vectors:
        return lexical_shortlist(company_description, grants, limit=limit)
    company_vector = company_vectors[0]

    scored: list[MatchCandidate] = []
    for grant in grants:
        vector = grant_embeddings.get(grant.id)
        if not vector:
            continue
        scored.append(
            MatchCandidate(
                grant=grant,
                shortlist_score=cosine_similarity(company_vector, vector),
            )
        )

    scored.sort(
        key=lambda candidate: (
            -candidate.shortlist_score,
            candidate.grant.deadline or "9999-12-31",
            candidate.grant.title,
        )
    )
    if scored:
        return scored[:limit]
    return lexical_shortlist(company_description, grants, limit=limit)


def build_grant_embeddings(
    grants: Sequence[GrantRecord],
    *,
    embedding_service: EmbeddingService,
    batch_size: int = 64,
) -> dict[str, list[float]]:
    if not grants:
        return {}

    embeddings: dict[str, list[float]] = {}
    for start in range(0, len(grants), batch_size):
        batch = list(grants[start : start + batch_size])
        texts = [grant.search_text or grant.title for grant in batch]
        vectors = embedding_service.embed_texts(texts)
        for grant, vector in zip(batch, vectors, strict=False):
            embeddings[grant.id] = vector
    return embeddings
