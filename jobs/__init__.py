"""Public job-board collection and normalization."""

from jobs.models import JobPosting
from jobs.service import JobSearchResult, search_jobs

__all__ = ["JobPosting", "JobSearchResult", "search_jobs"]

