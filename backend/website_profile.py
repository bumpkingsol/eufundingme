from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import requests
from openai import OpenAI
from pydantic import BaseModel

from .config import DEFAULT_OPENAI_TEXT_MODEL
from .openai_client import build_reasoning


DEFAULT_WEBSITE_FETCH_TIMEOUT_SECONDS = 10.0
DEFAULT_WEBSITE_USER_AGENT = (
    "Mozilla/5.0 (compatible; EUFundingMe/1.0; +https://eufunding.me)"
)
MIN_MEANINGFUL_WEBSITE_WORDS = 12
HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


@dataclass(slots=True)
class WebsiteContent:
    title: str | None
    meta_description: str | None
    body_text: str


@dataclass(slots=True)
class WebsiteProfileResolution:
    resolved: bool
    profile: str | None
    display_name: str | None
    source: str
    normalized_url: str | None
    message: str | None = None


class ExpandedWebsiteProfile(BaseModel):
    display_name: str
    profile: str


FetchHTML = Callable[[str], str]
GenerateWebsiteProfile = Callable[[str, WebsiteContent], tuple[str, str] | None]


def _validate_website_netloc(parsed) -> None:
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("malformed website url") from exc

    hostname = parsed.hostname
    if not hostname or any(ch.isspace() for ch in hostname):
        raise ValueError("malformed website url")

    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("malformed website url") from exc

    if hostname.endswith("."):
        hostname = hostname[:-1]

    labels = hostname.split(".")
    if any(not label for label in labels):
        raise ValueError("malformed website url")

    for label in labels:
        if not HOST_LABEL_PATTERN.fullmatch(label):
            raise ValueError("malformed website url")


def normalize_website_url(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("website url must not be empty")

    parts = urlsplit(normalized)
    if parts.scheme:
        if parts.scheme.lower() not in {"http", "https"}:
            raise ValueError("unsupported scheme for website url")
        _validate_website_netloc(parts)
        return urlunsplit(parts)

    if normalized.startswith("//"):
        _validate_website_netloc(parts)
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))

    prefixed = f"https://{normalized}"
    parsed = urlsplit(prefixed)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("malformed website url")
    _validate_website_netloc(parsed)
    return urlunsplit(parsed)


class _WebsiteContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.body_parts: list[str] = []
        self._in_title = False
        self._in_head = False
        self._in_body = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
            return

        if tag == "head":
            self._in_head = True
            return

        if self._in_head and tag not in {"meta", "link", "base", "script", "style", "noscript", "title"}:
            self._in_head = False
            self._in_title = False

        if tag == "body":
            self._in_head = False
            self._in_title = False
            self._in_body = True
            return

        if tag == "meta":
            attributes = {name.lower(): value for name, value in attrs}
            name = attributes.get("name")
            if isinstance(name, str) and name.lower() == "description":
                content = attributes.get("content")
                if content and self.meta_description is None:
                    self.meta_description = content.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = False
            return

        if tag == "head":
            self._in_head = False
            return

        if tag == "body":
            self._in_body = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        text = data.strip()
        if not text:
            return

        if self._in_title:
            self.title_parts.append(text)
        elif not self._in_head:
            self.body_parts.append(text)


def extract_website_content(html: str) -> WebsiteContent:
    parser = _WebsiteContentParser()
    parser.feed(html)
    parser.close()

    title = " ".join(parser.title_parts).strip() or None
    body_text = " ".join(parser.body_parts).strip()
    return WebsiteContent(
        title=title,
        meta_description=parser.meta_description,
        body_text=body_text,
    )


def fetch_website_html(
    url: str,
    *,
    timeout_seconds: float = DEFAULT_WEBSITE_FETCH_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_WEBSITE_USER_AGENT,
    session: requests.Session | None = None,
) -> str:
    request_kwargs = {
        "timeout": timeout_seconds,
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": user_agent,
        },
    }
    response = session.get(url, **request_kwargs) if session is not None else requests.get(url, **request_kwargs)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise ValueError("website response was not HTML")
    html = response.text.strip()
    if not html:
        raise ValueError("website response body was empty")
    return html


def _count_meaningful_words(value: str) -> int:
    return len(value.split())


def _is_meaningful_content(content: WebsiteContent, *, minimum_words: int) -> bool:
    combined_text = " ".join(
        part
        for part in (content.title, content.meta_description, content.body_text)
        if part
    ).strip()
    return _count_meaningful_words(combined_text) >= minimum_words


class WebsiteProfileService:
    def __init__(
        self,
        *,
        fetch_html: FetchHTML,
        generate_profile: GenerateWebsiteProfile,
        minimum_words: int = MIN_MEANINGFUL_WEBSITE_WORDS,
    ) -> None:
        self.fetch_html = fetch_html
        self.generate_profile = generate_profile
        self.minimum_words = minimum_words

    def resolve(self, url: str) -> WebsiteProfileResolution:
        normalized_url = normalize_website_url(url)
        html = self.fetch_html(normalized_url)
        content = extract_website_content(html)
        if not _is_meaningful_content(content, minimum_words=self.minimum_words):
            raise ValueError("website content is too thin to generate a profile")

        generated = self.generate_profile(normalized_url, content)
        if generated is None:
            raise ValueError("website profile generation failed")

        display_name, profile = generated
        display_name = display_name.strip()
        profile = profile.strip()
        if not display_name or not profile:
            raise ValueError("website profile generation returned empty content")

        return WebsiteProfileResolution(
            resolved=True,
            profile=profile,
            display_name=display_name,
            source="website_profile",
            normalized_url=normalized_url,
            message=None,
        )


class OpenAIWebsiteProfileGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_OPENAI_TEXT_MODEL,
        client: OpenAI | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)
        self.reasoning_effort = reasoning_effort

    def generate(self, url: str, content: WebsiteContent) -> tuple[str, str] | None:
        completion = self.client.responses.parse(
            model=self.model,
            instructions=(
                "You expand a company website homepage into a concise company profile for EU grant matching. "
                "Return 4-6 factual sentences describing what the company builds, who it serves, and its strategic focus. "
                "Use the provided page text as evidence. Do not add marketing language or uncertainty."
            ),
            input=json.dumps(
                {
                    "normalized_url": url,
                    "title": content.title,
                    "meta_description": content.meta_description,
                    "body_text": content.body_text,
                },
                ensure_ascii=True,
            ),
            text_format=ExpandedWebsiteProfile,
            reasoning=build_reasoning(self.reasoning_effort),
        )
        parsed = completion.output_parsed
        if parsed is None:
            return None
        return parsed.display_name.strip(), parsed.profile.strip()
