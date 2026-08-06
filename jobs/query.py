"""Parse a compact user query into job keywords and a location filter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchQuery:
    keywords: str
    location: str


KNOWN_LOCATIONS = (
    "san francisco",
    "new york",
    "los angeles",
    "washington dc",
    "toronto",
    "vancouver",
    "montreal",
    "ottawa",
    "calgary",
    "boston",
    "chicago",
    "seattle",
    "austin",
    "denver",
    "london",
    "dublin",
    "berlin",
    "paris",
    "amsterdam",
    "singapore",
    "sydney",
    "remote",
)


def parse_search_query(value: str, *, location_override: str = "") -> SearchQuery:
    query = " ".join(value.split()).strip()
    if location_override.strip():
        return SearchQuery(query, location_override.strip())

    lowered = query.casefold()
    if " in " in lowered:
        split_at = lowered.rfind(" in ")
        return SearchQuery(query[:split_at].strip(), query[split_at + 4 :].strip())

    for location in sorted(KNOWN_LOCATIONS, key=len, reverse=True):
        suffix = f" {location}"
        if lowered.endswith(suffix):
            return SearchQuery(query[: -len(suffix)].strip(), query[-len(location) :])
        if lowered == location:
            return SearchQuery("", query)
    return SearchQuery(query, "")

