"""Preview and apply truthful, job-specific Google Docs resume edits."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from openai import OpenAI

from google_docs_reader import get_google_services

DEFAULT_MODEL = "gpt-5.6-luna"


@dataclass(frozen=True)
class Bullet:
    text: str
    start: int
    end: int


def get_bullet_paragraphs(doc_id: str) -> list[Bullet]:
    docs_service, _ = get_google_services()
    doc = docs_service.documents().get(documentId=doc_id).execute()
    results: list[Bullet] = []

    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph or "bullet" not in paragraph:
            continue

        text_parts: list[str] = []
        start_index = None
        end_index = None
        for run in paragraph.get("elements", []):
            if "textRun" not in run:
                continue
            text_parts.append(run["textRun"].get("content", ""))
            start_index = run["startIndex"] if start_index is None else start_index
            end_index = run["endIndex"]

        clean_text = "".join(text_parts).strip()
        if clean_text and start_index is not None and end_index is not None:
            results.append(Bullet(clean_text, start_index, end_index))
    return results


def improve_bullets(
    job_description: str,
    bullets: list[Bullet],
    *,
    client: OpenAI | None = None,
) -> list[str]:
    if not job_description.strip():
        raise ValueError("Job description cannot be empty.")
    if not bullets:
        return []

    api_client = client or OpenAI()
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    numbered = "\n".join(f"{index + 1}. {bullet.text}" for index, bullet in enumerate(bullets))
    schema = {
        "type": "object",
        "properties": {
            "bullets": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": len(bullets),
                "maxItems": len(bullets),
            }
        },
        "required": ["bullets"],
        "additionalProperties": False,
    }

    response = api_client.responses.create(
        model=model,
        instructions=(
            "You are a professional resume editor. Rewrite each bullet without changing facts. "
            "Never invent experience, metrics, tools, employers, degrees, or certifications. "
            "Keep the original order and return exactly one rewrite per input bullet. "
            "Each rewrite must be concise, professional, and at most 24 words."
        ),
        input=f"Job description:\n{job_description}\n\nResume bullets:\n{numbered}",
        text={
            "format": {
                "type": "json_schema",
                "name": "tailored_resume_bullets",
                "strict": True,
                "schema": schema,
            }
        },
    )
    payload = json.loads(response.output_text)
    improved = [text.strip().lstrip("-• ").strip() for text in payload["bullets"]]
    if len(improved) != len(bullets) or any(not text for text in improved):
        raise ValueError("The model returned an invalid set of bullet points.")
    return improved


def preview_tailoring(doc_id: str, job_description: str) -> tuple[list[Bullet], list[str]]:
    bullets = get_bullet_paragraphs(doc_id)
    if not bullets:
        return [], []
    return bullets, improve_bullets(job_description, bullets)


def apply_tailoring(doc_id: str, bullets: list[Bullet], improved_lines: list[str]) -> int:
    """Apply a previously previewed edit after the caller obtains user confirmation."""
    if len(bullets) != len(improved_lines):
        raise ValueError("Original and improved bullet counts must match.")
    if not bullets:
        return 0

    current_bullets = get_bullet_paragraphs(doc_id)
    if current_bullets != bullets:
        raise ValueError(
            "The document changed after this preview was generated. Create a new preview before applying."
        )

    docs_service, _ = get_google_services()
    requests = []
    for bullet, new_text in zip(reversed(bullets), reversed(improved_lines)):
        requests.extend(
            [
                {
                    "deleteContentRange": {
                        "range": {"startIndex": bullet.start, "endIndex": bullet.end - 1}
                    }
                },
                {"insertText": {"location": {"index": bullet.start}, "text": new_text}},
            ]
        )
    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    return len(bullets)
