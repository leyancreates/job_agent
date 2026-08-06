"""Lever public Postings API adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from jobs.models import JobPosting
from jobs.text import html_to_text
from jobs.urls import BoardReference


def _posted_date(raw_value) -> str | None:
    if not isinstance(raw_value, (int, float)):
        return None
    return datetime.fromtimestamp(raw_value / 1000, tz=timezone.utc).isoformat()


def fetch_lever_jobs(board: BoardReference, client: httpx.Client) -> list[JobPosting]:
    response = client.get(
        f"https://{board.api_host}/v0/postings/{board.token}",
        params={"mode": "json"},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()

    company = board.token.replace("-", " ").title()
    results = []
    for raw in response.json():
        categories = raw.get("categories") or {}
        description = raw.get("descriptionPlain") or html_to_text(raw.get("description"))
        results.append(
            JobPosting(
                company=company,
                title=raw.get("text", "Untitled role"),
                location=categories.get("location", "Not specified"),
                job_url=raw.get("hostedUrl") or raw.get("applyUrl", ""),
                source="Lever",
                posted_date=_posted_date(raw.get("createdAt")),
                job_description=description or "",
            )
        )
    return results

