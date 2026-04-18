from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import GrantRecord, SnapshotEnvelope

logger = logging.getLogger(__name__)


def grant_to_snapshot_payload(grant: GrantRecord) -> dict[str, object]:
    return {
        "id": grant.id,
        "title": grant.title,
        "status": grant.status,
        "portal_url": grant.portal_url,
        "deadline": grant.deadline,
        "deadline_at": grant.deadline_at.isoformat() if grant.deadline_at is not None else None,
        "budget_display": grant.budget_display,
        "budget_amount_eur": grant.budget_amount_eur,
        "keywords": list(grant.keywords),
        "framework_programme": grant.framework_programme,
        "programme_division": grant.programme_division,
        "description": grant.description,
        "call_identifier": grant.call_identifier,
        "action_type": grant.action_type,
        "search_text": grant.search_text,
    }


def grant_from_snapshot_payload(payload: dict[str, object]) -> GrantRecord:
    deadline_at = payload.get("deadline_at")
    return GrantRecord(
        id=str(payload.get("id", "")),
        title=str(payload.get("title", "")),
        status=str(payload.get("status", "")),
        portal_url=str(payload.get("portal_url", "")),
        deadline=payload.get("deadline") if isinstance(payload.get("deadline"), str) else None,
        deadline_at=datetime.fromisoformat(deadline_at) if isinstance(deadline_at, str) and deadline_at else None,
        budget_display=payload.get("budget_display") if isinstance(payload.get("budget_display"), str) else None,
        budget_amount_eur=payload.get("budget_amount_eur") if isinstance(payload.get("budget_amount_eur"), int) else None,
        keywords=[str(keyword) for keyword in payload.get("keywords", []) if isinstance(keyword, str)],
        framework_programme=payload.get("framework_programme")
        if isinstance(payload.get("framework_programme"), str)
        else None,
        programme_division=payload.get("programme_division")
        if isinstance(payload.get("programme_division"), str)
        else None,
        description=payload.get("description") if isinstance(payload.get("description"), str) else None,
        call_identifier=payload.get("call_identifier") if isinstance(payload.get("call_identifier"), str) else None,
        action_type=payload.get("action_type") if isinstance(payload.get("action_type"), str) else None,
        search_text=str(payload.get("search_text", "")),
    )


class IndexSnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> SnapshotEnvelope | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return SnapshotEnvelope.model_validate(payload)
        except Exception:
            logger.exception("Failed to load index snapshot", extra={"path": str(self.path)})
            return None

    def save(
        self,
        *,
        grants: list[GrantRecord],
        embeddings: dict[str, list[float]],
        status_payload: dict[str, object],
        written_at: datetime | None = None,
    ) -> None:
        envelope = SnapshotEnvelope(
            grants=[grant_to_snapshot_payload(grant) for grant in grants],
            embeddings=embeddings,
            status_payload=status_payload,
            written_at=(written_at or datetime.now(timezone.utc)).isoformat(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp_path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
        tmp_path.replace(self.path)
