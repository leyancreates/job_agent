"""Public job-board collection and normalization."""

from .models import JobPosting
from .query import SearchQuery, parse_search_query
from .registry import BoardEntry, entry_from_url, load_registry
from .service import JobSearchResult, search_job_boards, search_jobs

__all__ = [
    "BoardEntry",
    "JobPosting",
    "JobSearchResult",
    "SearchQuery",
    "entry_from_url",
    "load_registry",
    "parse_search_query",
    "search_job_boards",
    "search_jobs",
]
