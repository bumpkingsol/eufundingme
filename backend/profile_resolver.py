from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel

DEMO_PROFILES_DEFAULT_NAME = "DEMO-PROFILES.md"
PROFILE_SECTION_PATTERN = re.compile(
    r"^##\s+\d+\.\s+(?P<name>.+?)(?:\s+\(.*?\))?\n\n\*\*Description:\*\*\n(?P<description>.*?)\n\n\*\*Expected matches:\*\*",
    re.MULTILINE | re.DOTALL,
)


def normalize_company_query(value: str) -> str:
    return " ".join(value.strip().lower().split())


@dataclass(slots=True)
class ProfileResolution:
    resolved: bool
    profile: str | None
    display_name: str | None
    source: str
    message: str | None


class ExpandedCompanyProfile(BaseModel):
    display_name: str
    profile: str


class OpenAICompanyProfileExpander:
    def __init__(self, *, api_key: str, model: str = "gpt-4o-2024-08-06", client: OpenAI | None = None) -> None:
        self.model = model
        self.client = client or OpenAI(api_key=api_key)

    def expand(self, query: str) -> tuple[str, str] | None:
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You expand a company name into a concise company profile for EU grant matching. "
                        "Return 4-6 factual sentences describing what the company builds, who it serves, "
                        "and its strategic focus areas. Do not mention uncertainty."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Company name: {query}",
                },
            ],
            response_format=ExpandedCompanyProfile,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            return None
        return parsed.display_name.strip(), parsed.profile.strip()


def resolve_demo_profiles_path() -> Path:
    env_override = os.getenv("DEMO_PROFILES_PATH")
    if env_override:
        configured = Path(env_override).expanduser().resolve()
        if configured.exists():
            return configured

    package_path = (Path(__file__).resolve().parent / DEMO_PROFILES_DEFAULT_NAME).resolve()
    if package_path.exists():
        return package_path

    parent_candidates = [
        Path(__file__).resolve().parents[2] / DEMO_PROFILES_DEFAULT_NAME,
        Path(__file__).resolve().parents[3] / DEMO_PROFILES_DEFAULT_NAME,
        Path(__file__).resolve().parents[4] / DEMO_PROFILES_DEFAULT_NAME,
        Path(__file__).resolve().parents[5] / DEMO_PROFILES_DEFAULT_NAME,
    ]
    for candidate in parent_candidates:
        if candidate.exists():
            return candidate

    fallback = Path.cwd() / DEMO_PROFILES_DEFAULT_NAME
    return fallback


def load_demo_profiles(markdown_path: Path | None = None) -> dict[str, tuple[str, str]]:
    markdown_path = markdown_path or resolve_demo_profiles_path()
    if not markdown_path.exists():
        return {}

    content = markdown_path.read_text(encoding="utf-8")
    profiles: dict[str, tuple[str, str]] = {}
    for match in PROFILE_SECTION_PATTERN.finditer(content):
        display_name = match.group("name").strip()
        description = " ".join(line.strip() for line in match.group("description").splitlines() if line.strip())
        profiles[normalize_company_query(display_name)] = (display_name, description)
    return profiles


class DemoProfileResolver:
    def __init__(
        self,
        *,
        profiles: dict[str, tuple[str, str]] | None = None,
        expander: object | None = None,
    ) -> None:
        self.profiles = profiles or load_demo_profiles()
        self.expander = expander

    def resolve(self, query: str) -> ProfileResolution:
        normalized_query = normalize_company_query(query)
        if not normalized_query:
            return ProfileResolution(
                resolved=False,
                profile=None,
                display_name=None,
                source="unresolved",
                message="Add one or two sentences about what the company does.",
            )

        profile = self.profiles.get(normalized_query)
        if profile is not None:
            display_name, description = profile
            return ProfileResolution(
                resolved=True,
                profile=description,
                display_name=display_name,
                source="demo_profile",
                message=None,
            )

        if self.expander is not None:
            expanded = self.expander.expand(query)
            if expanded is not None:
                display_name, description = expanded
                return ProfileResolution(
                    resolved=True,
                    profile=description,
                    display_name=display_name,
                    source="llm_expansion",
                    message=None,
                )

        return ProfileResolution(
            resolved=False,
            profile=None,
            display_name=None,
            source="unresolved",
            message="Could not expand company name automatically. Add one or two sentences about what the company does.",
        )
