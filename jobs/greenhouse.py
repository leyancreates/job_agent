"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

import httpx

from jobs.models import JobPosting
from jobs.text import html_to_text
from jobs.urls import BoardReference


def fetch_greenhouse_jobs(
    board: BoardReference, client: httpx.Client, *, company: str | None = None
) -> list[JobPosting]:
    base_url = f"https://{board.api_host}/v1/boards/{board.token}"
    if not company:
        board_response = client.get(base_url)
        board_response.raise_for_status()
        company = board_response.json().get("name")
    jobs_response = client.get(f"{base_url}/jobs", params={"content": "true"})
    jobs_response.raise_for_status()
    payload = jobs_response.json()
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise ValueError("Greenhouse returned an invalid jobs payload.")

    company = company or board.token.replace("-", " ").title()
    results = []
    for raw in raw_jobs:
        results.append(
            JobPosting(
                company=company,
                title=raw.get("title", "Untitled role"),
                location=(raw.get("location") or {}).get("name", "Not specified"),
                job_url=raw.get("absolute_url", ""),
                source="Greenhouse",
                posted_date=raw.get("updated_at"),
                job_description=html_to_text(raw.get("content")),
            )
        )
    return results
