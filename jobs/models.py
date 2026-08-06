"""Normalized job posting model shared by all sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class JobPosting:
    company: str
    title: str
    location: str
    job_url: str
    source: str
    posted_date: str | None
    job_description: str
    relevance_score: int = 0
    matched_terms: tuple[str, ...] = ()
    match_type: str | None = None

    @property
    def dedupe_key(self) -> tuple[str, ...]:
        parsed = urlsplit(self.job_url)
        canonical_url = urlunsplit(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
        )
        if canonical_url:
            return (canonical_url,)
        return tuple(
            value.casefold().strip() for value in (self.company, self.title, self.location)
        )

    def to_dict(self) -> dict[str, str | int | None]:
        payload = asdict(self)
        payload["matched_terms"] = ", ".join(self.matched_terms)
        return payload
