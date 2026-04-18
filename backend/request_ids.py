from __future__ import annotations

import uuid


def resolve_request_id(request_id: str | None = None) -> str:
    """
    Return the supplied request ID when provided, otherwise generate a new UUID4 hex value.
    """

    if request_id and request_id.strip():
        return request_id
    return uuid.uuid4().hex
