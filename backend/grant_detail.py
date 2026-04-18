from __future__ import annotations

import re
from html import unescape

from .models import GrantDetailResponse

_TAG_RE = re.compile(r"<[^>]+>")
_LIST_ITEM_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)


def _clean_html_text(value: str) -> str:
    text = _TAG_RE.sub(" ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_clean_html_text(str(item)) for item in value if _clean_html_text(str(item))]
    if not isinstance(value, str):
        return []
    list_items = [_clean_html_text(match) for match in _LIST_ITEM_RE.findall(value)]
    if list_items:
        return [item for item in list_items if item]
    cleaned = _clean_html_text(value)
    return [cleaned] if cleaned else []


def normalize_topic_detail_payload(payload: dict[str, object], *, topic_id: str) -> GrantDetailResponse:
    topic_details = payload.get("topicDetails") if isinstance(payload, dict) else None
    topic_details = topic_details if isinstance(topic_details, dict) else {}
    summary = topic_details.get("summary") if isinstance(topic_details.get("summary"), dict) else {}
    sections = topic_details.get("sections") if isinstance(topic_details.get("sections"), dict) else {}

    full_description = _clean_html_text(str(sections.get("objective", "")))
    expected_outcomes = _extract_list(sections.get("expectedOutcomes"))
    eligibility_criteria = _extract_list(sections.get("eligibilityConditions"))

    submission_conditions = (
        sections.get("submissionConditions")
        if isinstance(sections.get("submissionConditions"), dict)
        else {}
    )
    deadline_source = submission_conditions.get("deadlineDate") or summary.get("deadlineDate")
    submission_deadlines: list[dict[str, str]] = []
    if isinstance(deadline_source, str) and deadline_source:
        submission_deadlines.append(
            {
                "label": "Main deadline",
                "value": deadline_source[:10],
            }
        )

    documents_payload = sections.get("documents")
    documents: list[dict[str, str]] = []
    if isinstance(documents_payload, list):
        for item in documents_payload:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            if isinstance(title, str) and isinstance(url, str):
                documents.append({"title": title, "url": url})

    return GrantDetailResponse(
        grant_id=topic_id,
        full_description=full_description,
        eligibility_criteria=eligibility_criteria,
        submission_deadlines=submission_deadlines,
        expected_outcomes=expected_outcomes,
        documents=documents,
        partner_search_available=bool(sections.get("partnerSearch")),
        source="browser_topic_detail",
        fallback_used=False,
    )
