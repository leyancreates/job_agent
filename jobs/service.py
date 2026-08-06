"""Concurrent job-board collection, filtering, ranking, and deduplication."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from collections.abc import Callable

import httpx

from jobs.cache import PUBLIC_BOARD_CACHE, TTLCache
from jobs.models import JobPosting
from jobs.providers import get_provider_adapter
from jobs.query import SearchQuery
from jobs.relevance import MIN_RELEVANCE_SCORE, evaluate_relevance
from jobs.registry import BoardEntry, entry_from_url
from jobs.urls import UnsupportedJobBoardError

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class JobSearchResult:
    jobs: list[JobPosting]
    warnings: list[str]
    companies_checked: int
    total_companies: int
    categories_checked: dict[str, int] = field(default_factory=dict)


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
    query: SearchQuery,
    *,
    retries: int,
    sleep: Callable[[float], None],
) -> list[JobPosting]:
    adapter = get_provider_adapter(entry.provider)
    key: tuple[str, ...] = (entry.provider, entry.identifier)
    if adapter.query_scoped_cache:
        key += (" ".join(query.keywords.casefold().split()),)

    def load() -> list[JobPosting]:
        for attempt in range(retries + 1):
            try:
                board = entry.board_reference()
                return adapter.fetch_jobs(
                    board,
                    client,
                    company=entry.company,
                    query=query,
                )
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
    return evaluate_relevance(job, query).score


def _posted_timestamp(value: str | None) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def filter_rank_dedupe(jobs: list[JobPosting], query: SearchQuery) -> list[JobPosting]:
    unique: dict[tuple[str, ...], JobPosting] = {}
    for job in jobs:
        match = evaluate_relevance(job, query)
        keyword_match = not query.keywords.strip() or (
            match.all_terms_matched and match.score >= MIN_RELEVANCE_SCORE
        )
        if not job.job_url or not keyword_match or not _location_matches(job, query.location):
            continue
        scored_job = replace(
            job,
            relevance_score=match.score,
            matched_terms=match.matched_terms,
            match_type=match.match_type,
        )
        existing = unique.get(job.dedupe_key)
        if existing is None or (
            scored_job.relevance_score,
            _posted_timestamp(scored_job.posted_date),
        ) > (
            existing.relevance_score,
            _posted_timestamp(existing.posted_date),
        ):
            unique[job.dedupe_key] = scored_job
    return sorted(
        unique.values(),
        key=lambda job: (job.relevance_score, _posted_timestamp(job.posted_date)),
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
    categories_checked = dict(Counter(entry.category for entry in entries))
    if not entries:
        return JobSearchResult([], [], 0, 0, {})

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
                    query,
                    retries=retries,
                    sleep=sleep,
                ): entry
                for entry in entries
            }
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    collected.extend(future.result())
                except UnsupportedJobBoardError as exc:
                    label = entry.company or entry.identifier
                    warnings.append(f"{label}: {exc}")
                except (httpx.HTTPError, ValueError, TypeError):
                    label = entry.company or entry.identifier
                    provider_name = {
                        "smartrecruiters": "SmartRecruiters",
                    }.get(entry.provider, entry.provider.title())
                    warnings.append(
                        f"{label} ({provider_name}) is temporarily unavailable."
                    )
                checked += 1
                if progress_callback:
                    progress_callback(checked, total)
    finally:
        if owns_client:
            http_client.close()

    return JobSearchResult(
        filter_rank_dedupe(collected, query),
        warnings,
        checked,
        total,
        categories_checked,
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
        result.categories_checked,
    )
