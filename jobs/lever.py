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


def fetch_lever_jobs(
    board: BoardReference, client: httpx.Client, *, company: str | None = None
) -> list[JobPosting]:
    response = client.get(
        f"https://{board.api_host}/v0/postings/{board.token}",
        params={"mode": "json"},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Lever returned an invalid jobs payload.")

    company = company or board.token.replace("-", " ").title()
    results = []
    for raw in payload:
        categories = raw.get("categories") or {}
        all_locations = categories.get("allLocations") or []
        location = ", ".join(dict.fromkeys(all_locations)) or categories.get(
            "location", "Not specified"
        )
        description = raw.get("descriptionPlain") or html_to_text(raw.get("description"))
        results.append(
            JobPosting(
                company=company,
                title=raw.get("text", "Untitled role"),
                location=location,
                job_url=raw.get("hostedUrl") or raw.get("applyUrl", ""),
                source="Lever",
                posted_date=_posted_date(raw.get("createdAt")),
                job_description=description or "",
            )
        )
    return results
