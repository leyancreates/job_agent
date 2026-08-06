"""Ashby public Job Postings API adapter."""

from __future__ import annotations

import httpx

from jobs.models import JobPosting
from jobs.query import SearchQuery
from jobs.text import html_to_text
from jobs.urls import BoardReference


def fetch_ashby_jobs(
    board: BoardReference,
    client: httpx.Client,
    *,
    company: str | None = None,
    query: SearchQuery | None = None,
) -> list[JobPosting]:
    del query
    response = client.get(
        f"https://{board.api_host}/posting-api/job-board/{board.token}",
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise ValueError("Ashby returned an invalid jobs payload.")

    organization = company or board.token.replace("-", " ").title()
    results: list[JobPosting] = []
    for raw in raw_jobs:
        if raw.get("isListed") is False:
            continue
        locations = [raw.get("location", "")]
        locations.extend(
            item.get("location", "")
            for item in raw.get("secondaryLocations") or []
            if isinstance(item, dict)
        )
        if raw.get("isRemote") and not any(
            "remote" in value.casefold() for value in locations if value
        ):
            locations.append("Remote")
        location = ", ".join(dict.fromkeys(value for value in locations if value))
        description = raw.get("descriptionPlain") or html_to_text(
            raw.get("descriptionHtml")
        )
        results.append(
            JobPosting(
                company=organization,
                title=raw.get("title", "Untitled role"),
                location=location or "Not specified",
                job_url=raw.get("jobUrl") or raw.get("applyUrl", ""),
                source="Ashby",
                posted_date=raw.get("publishedAt"),
                job_description=description or "",
            )
        )
    return results
