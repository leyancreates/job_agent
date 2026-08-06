"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

import httpx

from jobs.models import JobPosting
from jobs.text import html_to_text
from jobs.urls import BoardReference


def fetch_greenhouse_jobs(board: BoardReference, client: httpx.Client) -> list[JobPosting]:
    base_url = f"https://{board.api_host}/v1/boards/{board.token}"
    board_response = client.get(base_url)
    board_response.raise_for_status()
    jobs_response = client.get(f"{base_url}/jobs", params={"content": "true"})
    jobs_response.raise_for_status()

    company = board_response.json().get("name") or board.token.replace("-", " ").title()
    results = []
    for raw in jobs_response.json().get("jobs", []):
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

