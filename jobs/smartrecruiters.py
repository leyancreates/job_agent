"""SmartRecruiters public Posting API adapter."""

from __future__ import annotations

import re

import httpx

from jobs.models import JobPosting
from jobs.query import SearchQuery
from jobs.relevance import title_has_query_signal
from jobs.text import html_to_text
from jobs.urls import BoardReference

PAGE_SIZE = 100
MAX_POSTINGS = 500
MAX_DETAIL_REQUESTS = 12


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _summary(raw: dict) -> str:
    labels: list[str] = []
    for key in ("industry", "department", "function"):
        value = raw.get(key) or {}
        if isinstance(value, dict) and value.get("label"):
            labels.append(str(value["label"]))
    return ". ".join(dict.fromkeys(labels))


def _description(raw: dict) -> str:
    sections = ((raw.get("jobAd") or {}).get("sections") or {})
    if not isinstance(sections, dict):
        return _summary(raw)
    parts = []
    for section in sections.values():
        if isinstance(section, dict) and section.get("text"):
            text = html_to_text(section["text"])
            if text:
                parts.append(text)
    return "\n\n".join(parts) or _summary(raw)


def _location(raw: dict) -> str:
    location = raw.get("location") or {}
    if not isinstance(location, dict):
        return "Not specified"
    value = location.get("fullLocation") or ", ".join(
        str(location.get(key))
        for key in ("city", "region", "country")
        if location.get(key)
    )
    if location.get("remote") and "remote" not in value.casefold():
        value = f"{value}, Remote" if value else "Remote"
    return value or "Not specified"


def _posting_url(board: BoardReference, raw: dict) -> str:
    if raw.get("postingUrl"):
        return str(raw["postingUrl"])
    identifier = ((raw.get("company") or {}).get("identifier") or board.token)
    posting_id = raw.get("id", "")
    return (
        f"https://jobs.smartrecruiters.com/{identifier}/{posting_id}-{_slug(raw.get('name', ''))}"
        if posting_id
        else ""
    )


def fetch_smartrecruiters_jobs(
    board: BoardReference,
    client: httpx.Client,
    *,
    company: str | None = None,
    query: SearchQuery | None = None,
) -> list[JobPosting]:
    base_url = f"https://{board.api_host}/v1/companies/{board.token}/postings"
    raw_jobs: list[dict] = []
    offset = 0
    total = 1
    while offset < total and offset < MAX_POSTINGS:
        response = client.get(
            base_url,
            params={"limit": PAGE_SIZE, "offset": offset, "destination": "PUBLIC"},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        page = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(page, list):
            raise ValueError("SmartRecruiters returned an invalid jobs payload.")
        raw_jobs.extend(item for item in page if isinstance(item, dict))
        total = min(int(payload.get("totalFound", len(raw_jobs))), MAX_POSTINGS)
        if not page:
            break
        offset += len(page)

    detail_requests = 0
    results: list[JobPosting] = []
    for raw in raw_jobs:
        detail = raw
        needs_detail = bool(
            query
            and query.keywords.strip()
            and title_has_query_signal(raw.get("name", ""), query)
            and detail_requests < MAX_DETAIL_REQUESTS
        )
        if needs_detail and raw.get("id"):
            detail_requests += 1
            try:
                response = client.get(f"{base_url}/{raw['id']}")
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    detail = payload
            except (httpx.HTTPError, ValueError, TypeError):
                detail = raw

        raw_company = (detail.get("company") or {}).get("name")
        results.append(
            JobPosting(
                company=company or raw_company or board.token.replace("-", " ").title(),
                title=detail.get("name", "Untitled role"),
                location=_location(detail),
                job_url=_posting_url(board, detail),
                source="SmartRecruiters",
                posted_date=detail.get("releasedDate"),
                job_description=_description(detail),
            )
        )
    return results
