from __future__ import annotations

from collections.abc import Callable, Sequence

from openai import OpenAI
from pydantic import BaseModel, Field

from .models import GrantDetailResponse, GrantRecord, MatchResponse, MatchResult
from .openai_client import build_reasoning

LANGUAGE_NAMES = {
    "bg": "Bulgarian",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "hr": "Croatian",
    "hu": "Hungarian",
    "it": "Italian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mt": "Maltese",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sv": "Swedish",
}

COUNTRY_EVIDENCE = {
    "Austria": ("austria", "austrian", "osterreich", "österreich"),
    "Belgium": ("belgium", "belgian", "belgique", "belgie", "belgië"),
    "Bulgaria": ("bulgaria", "bulgarian", "българ"),
    "Croatia": ("croatia", "croatian", "hrvatska", "hrvatski"),
    "Cyprus": ("cyprus", "cypriot", "κύπρος"),
    "Czechia": ("czechia", "czech republic", "czech", "česko", "česk"),
    "Denmark": ("denmark", "danish", "danmark"),
    "Estonia": ("estonia", "estonian", "eesti"),
    "Finland": ("finland", "finnish", "suomi"),
    "France": ("france", "french"),
    "Germany": ("germany", "german", "deutschland", "deutsch"),
    "Greece": ("greece", "greek", "ελλάδα", "ελλην"),
    "Hungary": ("hungary", "hungarian", "magyarország", "magyar"),
    "Ireland": ("ireland", "irish", "éire"),
    "Italy": ("italy", "italian", "italia", "italiano"),
    "Latvia": ("latvia", "latvian", "latvija", "latvie"),
    "Lithuania": ("lithuania", "lithuanian", "lietuva", "lietuv"),
    "Malta": ("malta", "maltese"),
    "Netherlands": ("netherlands", "dutch", "nederland", "nederlands"),
    "Poland": ("poland", "polish", "polska", "polski"),
    "Portugal": ("portugal", "portuguese", "português"),
    "Romania": ("romania", "romanian", "românia", "român"),
    "Slovakia": ("slovakia", "slovak", "slovensko", "slovensk"),
    "Slovenia": ("slovenia", "slovenian", "slovenija", "slovenski"),
    "Spain": ("spain", "spanish", "españa", "español"),
    "Sweden": ("sweden", "swedish", "sverige", "svensk"),
}


class TranslationEntry(BaseModel):
    text: str


class TranslationBatch(BaseModel):
    translations: list[TranslationEntry] = Field(default_factory=list)


def language_name(language_code: str | None) -> str:
    if not language_code:
        return "the original language"
    return LANGUAGE_NAMES.get(language_code.lower(), language_code.upper())


def detect_country_context(*parts: str | None) -> str | None:
    haystack = " ".join(part for part in parts if part).lower()
    for country, evidence in COUNTRY_EVIDENCE.items():
        if any(token in haystack for token in evidence):
            return country
    return None


def build_translation_note(source_language: str, *evidence_parts: str | None) -> str:
    source_name = language_name(source_language)
    country = detect_country_context(*evidence_parts)
    if country:
        return f"Translated from {source_name}. This grant appears tied to {country}."
    return f"Translated from {source_name}. Original grant content was published in {source_name}."


class OpenAIGrantTranslator:
    def __init__(
        self,
        *,
        model: str,
        client: OpenAI,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = model
        self.client = client
        self.reasoning_effort = reasoning_effort

    def translate(self, source_language: str, texts: Sequence[str]) -> list[str]:
        completion = self.client.responses.parse(
            model=self.model,
            instructions=(
                "Translate each grant text snippet into concise, accurate English. "
                "Keep programme names, country references, and legal or eligibility wording precise. "
                "Return one translated text per input item in the same order."
            ),
            input=f"Source language: {language_name(source_language)}\nTexts: {list(texts)}",
            text_format=TranslationBatch,
            reasoning=build_reasoning(self.reasoning_effort),
        )
        parsed = completion.output_parsed
        if parsed is None:
            return list(texts)
        translated = [entry.text.strip() for entry in parsed.translations]
        return translated if len(translated) == len(texts) else list(texts)


class GrantTranslationService:
    def __init__(
        self,
        translator: Callable[[str, Sequence[str]], list[str]] | None = None,
    ) -> None:
        self.translator = translator

    def translate_match_response(
        self,
        response: MatchResponse,
        grants: Sequence[GrantRecord],
    ) -> MatchResponse:
        grants_by_id = {
            grant.id: grant
            for grant in grants
            if isinstance(grant, GrantRecord) or hasattr(grant, "id")
        }
        return response.model_copy(
            update={
                "results": [
                    self.translate_match_result(result, grants_by_id.get(result.grant_id))
                    for result in response.results
                ]
            }
        )

    def translate_match_result(
        self,
        result: MatchResult,
        grant: GrantRecord | None = None,
    ) -> MatchResult:
        source_language = (grant.source_language if grant is not None else result.source_language) or None
        if not source_language or source_language == "en":
            return result.model_copy(update={"source_language": source_language})

        translated_title = self._translate_texts(source_language, [result.title])[0]
        translation_note = build_translation_note(
            source_language,
            result.title,
            grant.title if grant is not None else None,
            grant.description if grant is not None else None,
            grant.call_identifier if grant is not None else None,
            grant.framework_programme if grant is not None else None,
            grant.programme_division if grant is not None else None,
            " ".join(grant.keywords) if grant is not None else None,
        )
        return result.model_copy(
            update={
                "title": translated_title,
                "source_language": source_language,
                "translated_from_source": True,
                "translation_note": translation_note,
            }
        )

    def translate_grant_detail(
        self,
        detail: GrantDetailResponse,
        *,
        grant: GrantRecord | None = None,
    ) -> GrantDetailResponse:
        source_language = detail.source_language or (grant.source_language if grant is not None else None)
        if not source_language or source_language == "en":
            return detail.model_copy(update={"source_language": source_language})

        texts: list[str] = []
        if detail.full_description:
            texts.append(detail.full_description)
        texts.extend(detail.eligibility_criteria)
        texts.extend(detail.expected_outcomes)
        texts.extend(document.get("title", "") for document in detail.documents)

        translated = self._translate_texts(source_language, texts)
        cursor = 0

        full_description = detail.full_description
        if detail.full_description:
            full_description = translated[cursor]
            cursor += 1

        eligibility = translated[cursor : cursor + len(detail.eligibility_criteria)]
        cursor += len(detail.eligibility_criteria)
        outcomes = translated[cursor : cursor + len(detail.expected_outcomes)]
        cursor += len(detail.expected_outcomes)
        document_titles = translated[cursor : cursor + len(detail.documents)]

        translated_documents = [
            {"title": title, "url": document["url"]}
            for title, document in zip(document_titles, detail.documents, strict=False)
        ]

        translation_note = build_translation_note(
            source_language,
            detail.full_description,
            grant.title if grant is not None else None,
            grant.description if grant is not None else None,
            " ".join(detail.eligibility_criteria),
            " ".join(detail.expected_outcomes),
            " ".join(document.get("title", "") for document in detail.documents),
        )

        return detail.model_copy(
            update={
                "full_description": full_description,
                "eligibility_criteria": eligibility,
                "expected_outcomes": outcomes,
                "documents": translated_documents,
                "source_language": source_language,
                "translated_from_source": True,
                "translation_note": translation_note,
            }
        )

    def _translate_texts(self, source_language: str, texts: Sequence[str]) -> list[str]:
        prepared = [text for text in texts if text]
        if not prepared or self.translator is None:
            return list(texts)

        translated_prepared = self.translator(source_language, prepared)
        if len(translated_prepared) != len(prepared):
            return list(texts)

        translated_iter = iter(translated_prepared)
        return [next(translated_iter) if text else text for text in texts]
