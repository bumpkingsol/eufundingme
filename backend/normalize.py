from __future__ import annotations

import json
import re
from datetime import datetime

from .models import GrantRecord

STATUS_MAP = {
    "31094501": "Open",
    "31094502": "Forthcoming",
    "31094503": "Closed",
}

PORTAL_URL_TEMPLATE = (
    "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{topic_id}"
)

FRAMEWORK_PROGRAMME_MAP = {
    "HORIZON": "Horizon Europe",
    "DIGITAL": "Digital Europe Programme",
    "ERASMUS": "Erasmus+",
    "CREA": "Creative Europe",
    "CERV": "Citizens, Equality, Rights and Values",
    "SMP-COSME": "Single Market Programme",
    "EU4H": "EU4Health",
    "LIFE": "LIFE Programme",
    "CEF": "Connecting Europe Facility",
    "EDF": "European Defence Fund",
    "ISF": "Internal Security Fund",
}

DIVISION_HINTS = {
    "HORIZON-HLTH": "Health",
    "HORIZON-EIC": "European Innovation Council",
    "HORIZON-EIE": "European Innovation Ecosystems",
    "HORIZON-WIDERA": "Widening Participation and Spreading Excellence",
    "HORIZON-INFRA": "Research Infrastructures",
    "HORIZON-MISS": "EU Missions",
    "HORIZON-JU": "Joint Undertakings",
    "DIGITAL-AI-DATA": "AI and Data",
    "DIGITAL-SKILLS": "Digital Skills",
    "DIGITAL-BESTUSE": "Best Use of Technologies",
    "DIGITAL-SUPPORT": "Support Actions",
}

CLUSTER_PATTERN = re.compile(r"HORIZON-CL(?P<cluster>[1-6])")


def normalize_grant(metadata: dict, result_url: str | None = None) -> GrantRecord:
    identifier = str(first_value(metadata.get("identifier")) or "").strip()
    title = str(first_value(metadata.get("title")) or "").strip() or "Untitled grant"
    status_code = str(first_value(metadata.get("status")) or "").strip()
    status = STATUS_MAP.get(status_code, status_code or "Unknown")
    deadline_at = parse_datetime(first_value(metadata.get("deadlineDate")))
    call_identifier = clean_text(first_value(metadata.get("callIdentifier")))
    framework_programme = normalize_framework_programme(
        clean_text(first_value(metadata.get("frameworkProgramme"))),
        identifier=identifier,
        call_identifier=call_identifier,
    )
    programme_division = normalize_programme_division(
        clean_text(first_value(metadata.get("programmeDivision"))),
        identifier=identifier,
        call_identifier=call_identifier,
    )
    description = clean_text(first_value(metadata.get("description")))
    keywords = normalize_keywords(
        metadata.get("keywords"),
        identifier=identifier,
        call_identifier=call_identifier,
    )
    budget_display, budget_amount_eur = extract_budget(metadata, identifier=identifier)
    search_parts = [
        title,
        framework_programme,
        programme_division,
        description,
        " ".join(keywords),
    ]

    return GrantRecord(
        id=identifier or "unknown-topic",
        title=title,
        status=status,
        portal_url=result_url or build_portal_url(identifier),
        source_language=normalize_language(first_value(metadata.get("language"))),
        deadline=deadline_at.strftime("%Y-%m-%d") if deadline_at else trim_date(first_value(metadata.get("deadlineDate"))),
        deadline_at=deadline_at,
        budget_display=budget_display,
        budget_amount_eur=budget_amount_eur,
        keywords=keywords,
        framework_programme=framework_programme,
        programme_division=programme_division,
        description=description,
        call_identifier=call_identifier,
        action_type=clean_text(first_value(metadata.get("typesOfAction"))),
        search_text=" ".join(part for part in search_parts if part).lower(),
    )


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    if isinstance(value, dict):
        if "0" in value:
            return value["0"]
        if 0 in value:
            return value[0]
        first_key = next(iter(value), None)
        return value[first_key] if first_key is not None else None
    return value


def normalize_keywords(
    value,
    *,
    identifier: str | None = None,
    call_identifier: str | None = None,
) -> list[str]:
    raw_values: list[str] = []
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = [clean_text(item) for item in value if clean_text(item)]
    elif isinstance(value, dict):
        raw_values = [clean_text(item) for item in value.values() if clean_text(item)]
    else:
        text = clean_text(value)
        raw_values = [text] if text else []

    seen: set[str] = set()
    normalized: list[str] = []
    blocked_values = {identifier or "", call_identifier or ""}

    for item in raw_values:
        if item in blocked_values:
            continue
        if is_code_like_label(item):
            continue
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(item)

    return normalized[:8]


def extract_budget(metadata: dict, identifier: str) -> tuple[str | None, int | None]:
    raw_budget = first_value(metadata.get("budgetOverview"))
    if not raw_budget:
        return None, None

    try:
        parsed = json.loads(raw_budget)
    except (TypeError, json.JSONDecodeError):
        return None, None

    topic_map = parsed.get("budgetTopicActionMap")
    if not isinstance(topic_map, dict):
        return None, None

    matched_totals: list[int] = []
    fallback_totals: list[int] = []

    for entries in topic_map.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            total = sum_budget_years(entry.get("budgetYearMap"))
            if total is None:
                continue
            action = str(entry.get("action") or "")
            topic_identifier = str(entry.get("topicIdentifier") or entry.get("identifier") or "")
            if identifier and (identifier == action or identifier == topic_identifier or identifier in action):
                matched_totals.append(total)
            else:
                fallback_totals.append(total)

    if matched_totals:
        amount = max(matched_totals)
    elif len(fallback_totals) == 1:
        amount = fallback_totals[0]
    else:
        return None, None

    return format_eur(amount), amount


def sum_budget_years(value) -> int | None:
    if not isinstance(value, dict):
        return None
    total = 0
    found_value = False
    for amount in value.values():
        try:
            total += int(float(str(amount)))
        except (TypeError, ValueError):
            continue
        found_value = True
    return total if found_value else None


def parse_datetime(value) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def trim_date(value) -> str | None:
    text = clean_text(value)
    return text[:10] if text else None


def clean_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_language(value) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return text.lower()


def is_numericish(value: str | None) -> bool:
    return bool(value and value.isdigit())


def normalize_framework_programme(
    value: str | None,
    *,
    identifier: str,
    call_identifier: str | None,
) -> str | None:
    if value and not is_numericish(value):
        return value

    key = identifier or call_identifier or ""
    for prefix, label in FRAMEWORK_PROGRAMME_MAP.items():
        if key.startswith(prefix):
            return label
    return value if value and not is_numericish(value) else None


def normalize_programme_division(
    value: str | None,
    *,
    identifier: str,
    call_identifier: str | None,
) -> str | None:
    if value and not is_numericish(value):
        return value

    key = identifier or call_identifier or ""
    cluster_match = CLUSTER_PATTERN.search(key)
    if cluster_match:
        return f"Cluster {cluster_match.group('cluster')}"

    for prefix, label in DIVISION_HINTS.items():
        if key.startswith(prefix):
            return label
    return value if value and not is_numericish(value) else None


def is_code_like_label(value: str | None) -> bool:
    if not value:
        return False
    compact = value.strip()
    if " " in compact:
        return False
    return compact.upper() == compact and "-" in compact and any(char.isdigit() for char in compact)


def build_portal_url(topic_id: str) -> str:
    return PORTAL_URL_TEMPLATE.format(topic_id=topic_id)


def format_eur(amount: int) -> str:
    if amount >= 1_000_000:
        formatted = f"{amount / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"EUR {formatted}M"
    if amount >= 1_000:
        formatted = f"{amount / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"EUR {formatted}K"
    return f"EUR {amount}"
