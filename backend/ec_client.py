from __future__ import annotations

import requests

SEARCH_ENDPOINT = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"


class ECSearchClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_key: str = "SEDIA",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.session = session or requests.Session()
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, *, text: str, page_number: int = 1, page_size: int = 100) -> dict:
        response = self.session.post(
            SEARCH_ENDPOINT,
            params={
                "apiKey": self.api_key,
                "text": text,
                "pageSize": page_size,
                "pageNumber": page_number,
            },
            json={"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}}]}},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("EC search API returned a non-object response")
        return payload
