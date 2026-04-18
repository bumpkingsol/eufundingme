from __future__ import annotations

import logging
import time

import requests
import sentry_sdk

SEARCH_ENDPOINT = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
logger = logging.getLogger(__name__)


class ECSearchClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_key: str = "SEDIA",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.session = session or requests.Session()
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)

    def search(self, *, text: str, page_number: int = 1, page_size: int = 100) -> dict:
        for attempt in range(self.max_retries + 1):
            try:
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
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                logger.warning(
                    "EC search request failed",
                    extra={
                        "text": text,
                        "page_number": page_number,
                        "page_size": page_size,
                        "attempt": attempt + 1,
                    },
                    exc_info=exc,
                )
                sentry_sdk.add_breadcrumb(
                    category="ec_search",
                    message="EC search request failed",
                    level="warning",
                    data={"text": text, "page_number": page_number, "attempt": attempt + 1},
                )
                if attempt >= self.max_retries:
                    sentry_sdk.capture_exception(exc)
                    raise
                if self.retry_backoff_seconds > 0:
                    time.sleep(self.retry_backoff_seconds * (attempt + 1))
