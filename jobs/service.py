"""Job-board orchestration, filtering, and deduplication."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from jobs.greenhouse import fetch_greenhouse_jobs
from jobs.lever import fetch_lever_jobs
from jobs.models import JobPosting
from jobs.urls import UnsupportedJobBoardError, parse_board_url


@dataclass(frozen=True)
class JobSearchResult:
    jobs: list[JobPosting]
    warnings: list[str]


def _matches(job: JobPosting, keywords: str, location: str) -> bool:
    keyword_tokens = [token.casefold() for token in keywords.split() if token]
    searchable = f"{job.company} {job.title} {job.job_description}".casefold()
    keyword_match = all(token in searchable for token in keyword_tokens)
    location_match = not location.strip() or location.casefold().strip() in job.location.casefold()
    return keyword_match and location_match


def search_jobs(
    board_urls: list[str],
    *,
    keywords: str = "",
    location: str = "",
    client: httpx.Client | None = None,
) -> JobSearchResult:
    jobs: list[JobPosting] = []
    warnings: list[str] = []
    owns_client = client is None
    http_client = client or httpx.Client(timeout=15, follow_redirects=True)

    try:
        for url in dict.fromkeys(value.strip() for value in board_urls if value.strip()):
            try:
                board = parse_board_url(url)
                fetcher = fetch_greenhouse_jobs if board.source == "Greenhouse" else fetch_lever_jobs
                jobs.extend(fetcher(board, http_client))
            except UnsupportedJobBoardError as exc:
                warnings.append(f"{url}: {exc}")
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                warnings.append(f"Could not load {url}: {type(exc).__name__}")
    finally:
        if owns_client:
            http_client.close()

    unique: dict[tuple[str, ...], JobPosting] = {}
    for job in jobs:
        if job.job_url and _matches(job, keywords, location):
            unique.setdefault(job.dedupe_key, job)
    return JobSearchResult(list(unique.values()), warnings)

