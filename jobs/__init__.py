"""Public job-board collection and normalization."""

from .models import JobPosting
from .query import SearchQuery, parse_search_query
from .registry import (
    CATEGORIES,
    SUPPORTED_PROVIDERS,
    BoardEntry,
    entry_from_url,
    load_registry,
)
from .service import JobSearchResult, search_job_boards, search_jobs

__all__ = [
    "BoardEntry",
    "CATEGORIES",
    "JobPosting",
    "JobSearchResult",
    "SearchQuery",
    "SUPPORTED_PROVIDERS",
    "entry_from_url",
    "load_registry",
    "parse_search_query",
    "search_job_boards",
    "search_jobs",
]
