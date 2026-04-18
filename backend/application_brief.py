from __future__ import annotations

import json
import time

import sentry_sdk
from openai import OpenAI
from pydantic import BaseModel

from .config import DEFAULT_OPENAI_TEXT_MODEL
from .grant_detail import build_fallback_grant_detail
from .models import (
    ApplicationBriefRequest,
    ApplicationBriefResponse,
    ApplicationBriefSections,
)
from .openai_client import build_reasoning


class _ApplicationBriefPayload(BaseModel):
    company_fit_summary: str
    key_requirements: list[str]
    suggested_consortium_partners: list[str]
    timeline: list[str]
    risks_and_gaps: list[str]


class ApplicationBriefService:
    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str = DEFAULT_OPENAI_TEXT_MODEL,
        reasoning_effort: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    def generate(
        self,
        *,
        company_description: str,
        match_result: dict,
        grant_detail: dict,
    ) -> ApplicationBriefResponse:
        started_at = time.perf_counter()
        request = ApplicationBriefRequest(
            company_description=company_description,
            match_result=match_result,
            grant_detail=grant_detail,
        )
        try:
            if self.client is None:
                with sentry_sdk.start_span(op="ai.application_brief", name="Application brief fallback") as span:
                    span.set_data("grant_id", request.match_result.grant_id)
                    span.set_data("fallback_used", True)
                    response = self._build_fallback_response(request)
                sentry_sdk.set_measurement("application_brief_fallback_used", 1.0)
                sentry_sdk.set_measurement("application_brief_failed", 0.0)
                return response

            with sentry_sdk.start_span(op="ai.application_brief", name="Application brief generation") as span:
                span.set_data("grant_id", request.match_result.grant_id)
                span.set_data("fallback_used", False)
                completion = self.client.responses.parse(
                    model=self.model,
                    instructions=(
                        "You draft an EU grant application brief. "
                        "Return concise, practical content grounded in the company profile, "
                        "match rationale, eligibility criteria, outcomes, and deadlines."
                    ),
                    input=json.dumps(
                        {
                            "company_description": request.company_description,
                            "match_result": request.match_result.model_dump(),
                            "grant_detail": request.grant_detail.model_dump(),
                        },
                        ensure_ascii=True,
                    ),
                    text_format=_ApplicationBriefPayload,
                    reasoning=build_reasoning(self.reasoning_effort),
                )
                parsed = completion.output_parsed
                if parsed is None:
                    raise RuntimeError("brief generation failed")

            sections = ApplicationBriefSections.model_validate(parsed.model_dump())
            sentry_sdk.set_measurement("application_brief_fallback_used", 0.0)
            sentry_sdk.set_measurement("application_brief_failed", 0.0)
            return build_application_brief_response(
                match_title=request.match_result.title,
                sections=sections,
            )
        except Exception:
            sentry_sdk.set_measurement("application_brief_failed", 1.0)
            raise
        finally:
            sentry_sdk.set_measurement(
                "application_brief_latency_ms",
                round((time.perf_counter() - started_at) * 1000, 3),
            )

    def _build_fallback_response(self, request: ApplicationBriefRequest) -> ApplicationBriefResponse:
        detail = request.grant_detail
        if detail.fallback_used and not detail.submission_deadlines:
            detail = build_fallback_grant_detail(request.match_result.model_dump())

        sections = ApplicationBriefSections(
            company_fit_summary=(
                f"{request.match_result.title} aligns with the company because the current fit score is "
                f"{request.match_result.fit_score}/100 and the recommended angle is "
                f"{request.match_result.application_angle.lower()}."
            ),
            key_requirements=detail.eligibility_criteria or [request.match_result.why_match],
            suggested_consortium_partners=[
                "Research institution with EU delivery experience",
                "Pilot customer from a priority market",
            ],
            timeline=_build_timeline(detail),
            risks_and_gaps=[
                "Need sharper proof of EU-wide impact",
                "Need named partners and implementation evidence",
            ],
        )
        return build_application_brief_response(
            match_title=request.match_result.title,
            sections=sections,
        )


def build_application_brief_response(
    *,
    match_title: str,
    sections: ApplicationBriefSections,
) -> ApplicationBriefResponse:
    markdown = "\n".join(
        [
            f"# {match_title} application brief",
            "",
            "## Company fit summary",
            sections.company_fit_summary,
            "",
            "## Key requirements",
            *[f"- {item}" for item in sections.key_requirements],
            "",
            "## Suggested consortium partners",
            *[f"- {item}" for item in sections.suggested_consortium_partners],
            "",
            "## Timeline",
            *[f"- {item}" for item in sections.timeline],
            "",
            "## Risks and gaps",
            *[f"- {item}" for item in sections.risks_and_gaps],
        ]
    )
    html = "\n".join(
        [
            "<article class=\"brief-export\">",
            f"<h1>{match_title} application brief</h1>",
            f"<section><h2>Company fit summary</h2><p>{sections.company_fit_summary}</p></section>",
            _render_html_list("Key requirements", sections.key_requirements),
            _render_html_list("Suggested consortium partners", sections.suggested_consortium_partners),
            _render_html_list("Timeline", sections.timeline),
            _render_html_list("Risks and gaps", sections.risks_and_gaps),
            "</article>",
        ]
    )
    return ApplicationBriefResponse(markdown=markdown, html=html, sections=sections)


def _render_html_list(title: str, items: list[str]) -> str:
    return (
        f"<section><h2>{title}</h2><ul>"
        + "".join(f"<li>{item}</li>" for item in items)
        + "</ul></section>"
    )


def _build_timeline(detail) -> list[str]:
    if detail.submission_deadlines:
        first_deadline = detail.submission_deadlines[0]
        deadline = first_deadline.get("value") if isinstance(first_deadline, dict) else first_deadline.value
        return [
            "Week 1: confirm scope and writing ownership",
            "Week 2: lock evidence pack and partner roles",
            f"Final week before {deadline}: finalise impact, budget, and compliance sections",
        ]
    return [
        "Week 1: confirm scope and writing ownership",
        "Week 2: lock evidence pack and partner roles",
        "Final week: finalise impact, budget, and compliance sections",
    ]
