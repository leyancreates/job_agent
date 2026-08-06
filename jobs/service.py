"""Concurrent job-board collection, filtering, ranking, and deduplication."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from collections.abc import Callable

import httpx

from jobs.cache import PUBLIC_BOARD_CACHE, TTLCache
from jobs.greenhouse import fetch_greenhouse_jobs
from jobs.lever import fetch_lever_jobs
from jobs.models import JobPosting
from jobs.query import SearchQuery
from jobs.registry import BoardEntry, entry_from_url
from jobs.urls import UnsupportedJobBoardError

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class JobSearchResult:
    jobs: list[JobPosting]
    warnings: list[str]
    companies_checked: int
    total_companies: int


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and (
        exc.response.status_code == 429 or exc.response.status_code >= 500
    )


def _fetch_board(
    entry: BoardEntry,
    client: httpx.Client,
    cache: TTLCache,
    *,
    retries: int,
    sleep: Callable[[float], None],
) -> list[JobPosting]:
    key = (entry.provider, entry.identifier)

    def load() -> list[JobPosting]:
        for attempt in range(retries + 1):
            try:
                board = entry.board_reference()
                fetcher = (
                    fetch_greenhouse_jobs
                    if entry.provider == "greenhouse"
                    else fetch_lever_jobs
                )
                return fetcher(board, client, company=entry.company)
            except httpx.HTTPError as exc:
                if attempt >= retries or not _retryable(exc):
                    raise
                sleep(0.2 * (2**attempt))
        return []

    return cache.get_or_load(key, load)


def _location_matches(job: JobPosting, location: str) -> bool:
    requested = location.casefold().strip()
    if not requested:
        return True
    if requested == "remote":
        return "remote" in job.location.casefold()
    return requested in job.location.casefold()


def relevance_score(job: JobPosting, query: SearchQuery) -> int:
    tokens = [token.casefold() for token in query.keywords.split() if token]
    title = job.title.casefold()
    description = job.job_description.casefold()
    score = sum(4 for token in tokens if token in title)
    score += sum(1 for token in tokens if token in description)
    if query.keywords.casefold() in title and query.keywords.strip():
        score += 5
    return score


def _posted_timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def filter_rank_dedupe(jobs: list[JobPosting], query: SearchQuery) -> list[JobPosting]:
    tokens = [token.casefold() for token in query.keywords.split() if token]
    unique: dict[tuple[str, ...], JobPosting] = {}
    for job in jobs:
        searchable = f"{job.title} {job.job_description}".casefold()
        if (
            job.job_url
            and all(token in searchable for token in tokens)
            and _location_matches(job, query.location)
        ):
            unique.setdefault(job.dedupe_key, job)
    return sorted(
        unique.values(),
        key=lambda job: (relevance_score(job, query), _posted_timestamp(job.posted_date)),
        reverse=True,
    )


def search_job_boards(
    entries: list[BoardEntry],
    query: SearchQuery,
    *,
    max_workers: int = 8,
    retries: int = 2,
    client: httpx.Client | None = None,
    cache: TTLCache = PUBLIC_BOARD_CACHE,
    progress_callback: ProgressCallback | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> JobSearchResult:
    entries = list({(entry.provider, entry.identifier): entry for entry in entries}.values())
    total = len(entries)
    if not entries:
        return JobSearchResult([], [], 0, 0)

    workers = max(1, min(max_workers, 12, total))
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=httpx.Timeout(12, connect=5),
        limits=httpx.Limits(max_connections=workers, max_keepalive_connections=workers),
        follow_redirects=True,
    )
    collected: list[JobPosting] = []
    warnings: list[str] = []
    checked = 0

    try:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job-board") as pool:
            futures = {
                pool.submit(
                    _fetch_board,
                    entry,
                    http_client,
                    cache,
                    retries=retries,
                    sleep=sleep,
                ): entry
                for entry in entries
            }
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    collected.extend(future.result())
                except (httpx.HTTPError, ValueError, TypeError):
                    label = entry.company or entry.identifier
                    warnings.append(f"{label} ({entry.provider.title()}) is temporarily unavailable.")
                checked += 1
                if progress_callback:
                    progress_callback(checked, total)
    finally:
        if owns_client:
            http_client.close()

    return JobSearchResult(
        filter_rank_dedupe(collected, query), warnings, checked, total
    )


def search_jobs(
    board_urls: list[str],
    *,
    keywords: str = "",
    location: str = "",
    client: httpx.Client | None = None,
) -> JobSearchResult:
    """Backward-compatible URL search used by the single-company workflow."""
    entries: list[BoardEntry] = []
    warnings: list[str] = []
    for url in board_urls:
        try:
            entries.append(entry_from_url(url))
        except UnsupportedJobBoardError as exc:
            warnings.append(f"{url}: {exc}")
    result = search_job_boards(
        entries,
        SearchQuery(keywords, location),
        client=client,
        retries=0,
    )
    return JobSearchResult(
        result.jobs,
        warnings + result.warnings,
        result.companies_checked,
        result.total_companies,
    )
