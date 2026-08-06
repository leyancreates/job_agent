"""Provider adapter interface and supported public API implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from jobs.ashby import fetch_ashby_jobs
from jobs.greenhouse import fetch_greenhouse_jobs
from jobs.lever import fetch_lever_jobs
from jobs.models import JobPosting
from jobs.query import SearchQuery
from jobs.smartrecruiters import fetch_smartrecruiters_jobs
from jobs.urls import BoardReference, UnsupportedJobBoardError


class JobProviderAdapter(Protocol):
    provider: str
    query_scoped_cache: bool

    def fetch_jobs(
        self,
        board: BoardReference,
        client: httpx.Client,
        *,
        company: str | None,
        query: SearchQuery,
    ) -> list[JobPosting]: ...


Fetcher = Callable[..., list[JobPosting]]


@dataclass(frozen=True)
class PublicApiAdapter:
    provider: str
    fetcher: Fetcher
    query_scoped_cache: bool = False

    def fetch_jobs(
        self,
        board: BoardReference,
        client: httpx.Client,
        *,
        company: str | None,
        query: SearchQuery,
    ) -> list[JobPosting]:
        return self.fetcher(board, client, company=company, query=query)


@dataclass(frozen=True)
class WorkdayPublicInterface:
    """Safe extension point; no generic, documented public Workday API is assumed."""

    provider: str = "workday"
    query_scoped_cache: bool = False

    def fetch_jobs(
        self,
        board: BoardReference,
        client: httpx.Client,
        *,
        company: str | None,
        query: SearchQuery,
    ) -> list[JobPosting]:
        del board, client, company, query
        raise UnsupportedJobBoardError(
            "Workday fetching is disabled until an employer exposes a documented, "
            "unauthenticated public jobs API."
        )


def _legacy_fetcher(fetcher: Fetcher) -> Fetcher:
    def wrapped(board, client, *, company=None, query=None):
        del query
        return fetcher(board, client, company=company)

    return wrapped


PROVIDER_ADAPTERS: dict[str, JobProviderAdapter] = {
    "greenhouse": PublicApiAdapter("greenhouse", _legacy_fetcher(fetch_greenhouse_jobs)),
    "lever": PublicApiAdapter("lever", _legacy_fetcher(fetch_lever_jobs)),
    "smartrecruiters": PublicApiAdapter(
        "smartrecruiters", fetch_smartrecruiters_jobs, query_scoped_cache=True
    ),
    "ashby": PublicApiAdapter("ashby", fetch_ashby_jobs),
    "workday": WorkdayPublicInterface(),
}


def get_provider_adapter(provider: str) -> JobProviderAdapter:
    try:
        return PROVIDER_ADAPTERS[provider.casefold()]
    except KeyError as exc:
        raise UnsupportedJobBoardError(f"Unsupported job-board provider: {provider}") from exc
