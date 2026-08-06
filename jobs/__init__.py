"""Public job-board collection and normalization."""

from jobs.models import JobPosting
from jobs.query import SearchQuery, parse_search_query
from jobs.registry import BoardEntry, entry_from_url, load_registry
from jobs.service import JobSearchResult, search_job_boards, search_jobs

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
