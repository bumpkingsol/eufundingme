from __future__ import annotations

import re
from html import unescape

import requests

from .models import GrantDetailResponse, GrantRecord

TOPIC_DETAILS_URL_TEMPLATE = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{topic_id}.json"
)

TAG_PATTERN = re.compile(r"<[^>]+>")
LIST_ITEM_PATTERN = re.compile(r"<li[^>]*>(.*?)</li>", flags=re.IGNORECASE | re.DOTALL)
WHITESPACE_PATTERN = re.compile(r"\s+")


def strip_html_to_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = TAG_PATTERN.sub(" ", unescape(value))
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_topic_detail_payload(payload: dict[str, object], *, topic_id: str) -> GrantDetailResponse:
    topic_details = payload.get("topicDetails") if isinstance(payload, dict) else None
    summary = topic_details.get("summary") if isinstance(topic_details, dict) else None
    sections = topic_details.get("sections") if isinstance(topic_details, dict) else None

    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(sections, dict):
        sections = {}

    return GrantDetailResponse(
        grant_id=str(summary.get("identifier") or topic_id),
        full_description=strip_html_to_text(sections.get("objective") or sections.get("description")),
        eligibility_criteria=_normalize_text_list(sections.get("eligibilityConditions")),
        submission_deadlines=_normalize_deadlines(sections.get("submissionConditions"), summary),
        expected_outcomes=_normalize_text_list(sections.get("expectedOutcomes")),
        documents=_normalize_documents(sections.get("documents")),
        partner_search_available=_normalize_bool(sections.get("partnerSearch")),
        source="browser_topic_detail",
        fallback_used=False,
    )


def build_fallback_grant_detail(match_result: dict[str, object]) -> GrantDetailResponse:
    deadline = match_result.get("deadline")
    return GrantDetailResponse(
        grant_id=str(match_result.get("grant_id") or ""),
        full_description=str(match_result.get("description") or ""),
        source_language=match_result.get("source_language") if isinstance(match_result.get("source_language"), str) else None,
        translated_from_source=bool(match_result.get("translated_from_source")),
        translation_note=match_result.get("translation_note") if isinstance(match_result.get("translation_note"), str) else None,
        detail_note=match_result.get("detail_note") if isinstance(match_result.get("detail_note"), str) else None,
        eligibility_criteria=[],
        submission_deadlines=(
            [{"label": "Main deadline", "value": deadline}]
            if isinstance(deadline, str) and deadline
            else []
        ),
        expected_outcomes=[],
        documents=[],
        partner_search_available=None,
        source="match_result_fallback",
        fallback_used=True,
    )


def build_grant_record_fallback(
    grant: GrantRecord,
    *,
    source: str = "indexed_grant_fallback",
    detail_note: str | None = None,
) -> GrantDetailResponse:
    return GrantDetailResponse(
        grant_id=grant.id,
        full_description=grant.description or "",
        source_language=grant.source_language,
        detail_note=detail_note,
        eligibility_criteria=[],
        submission_deadlines=(
            [{"label": "Main deadline", "value": grant.deadline}]
            if isinstance(grant.deadline, str) and grant.deadline
            else []
        ),
        expected_outcomes=[],
        documents=[],
        partner_search_available=None,
        source=source,
        fallback_used=True,
    )


def _normalize_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        values = value
    elif value is None:
        values = []
    else:
        values = [value]

    items: list[str] = []
    for entry in values:
        if isinstance(entry, str) and "<li" in entry.lower():
            items.extend(_extract_list_items(entry))
            continue
        text = strip_html_to_text(entry)
        if text:
            items.append(text)
    return list(dict.fromkeys(items))


def _extract_list_items(value: str) -> list[str]:
    parts = LIST_ITEM_PATTERN.findall(value)
    if not parts:
        text = strip_html_to_text(value)
        return [text] if text else []
    return [item for part in parts if (item := strip_html_to_text(part))]


def _normalize_deadlines(value: object, summary: dict[str, object]) -> list[dict[str, str]]:
    deadlines: list[tuple[str, str]] = []
    if isinstance(value, dict):
        detail_deadline = _date_only(value.get("deadlineDate"))
        if detail_deadline:
            deadlines.append(("Main deadline", detail_deadline))
    summary_deadline = _date_only(summary.get("deadlineDate"))
    if summary_deadline and ("Main deadline", summary_deadline) not in deadlines:
        deadlines.append(("Main deadline", summary_deadline))
    return [{"label": label, "value": deadline} for label, deadline in deadlines]


def _normalize_documents(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    documents: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        url = item.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            documents.append({"title": title, "url": url})
    return documents


def _normalize_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _date_only(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


class GrantDetailService:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def get(self, topic_id: str) -> GrantDetailResponse:
        response = self.session.get(
            TOPIC_DETAILS_URL_TEMPLATE.format(topic_id=topic_id),
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            raise LookupError(f"no grant detail found for {topic_id}")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise LookupError(f"no grant detail found for {topic_id}")
        detail = normalize_topic_detail_payload(payload, topic_id=topic_id)
        return detail.model_copy(update={"source": "topic_detail_json"})
