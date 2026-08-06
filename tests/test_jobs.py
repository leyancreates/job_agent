import threading
import time

import httpx

from jobs.cache import TTLCache
from jobs.models import JobPosting
from jobs.query import SearchQuery, parse_search_query
from jobs.registry import BoardEntry, load_registry
from jobs.service import filter_rank_dedupe, search_job_boards, search_jobs
from jobs.urls import parse_board_url


def lever_entry(identifier: str, company: str | None = None) -> BoardEntry:
    return BoardEntry(
        company=company or identifier.title(),
        provider="lever",
        identifier=identifier,
        url=f"https://jobs.lever.co/{identifier}",
        verified_at="test",
    )


def lever_job(identifier: str, title: str = "Data Analyst", location: str = "Remote"):
    return {
        "text": title,
        "categories": {"location": location, "allLocations": [location]},
        "hostedUrl": f"https://jobs.lever.co/{identifier}/job-1",
        "createdAt": 1751328000000,
        "descriptionPlain": "Analyze data with Python and SQL.",
    }


def test_registry_has_at_least_fifty_verified_unique_boards():
    entries = load_registry()
    keys = {(entry.provider, entry.identifier) for entry in entries}
    assert len(entries) >= 50
    assert len(keys) == len(entries)
    assert {entry.provider for entry in entries} == {"greenhouse", "lever"}
    assert all(entry.verified_at == "2026-08-05" for entry in entries)
    assert all("linkedin" not in entry.url and "indeed" not in entry.url for entry in entries)


def test_query_parser_extracts_location_and_supports_remote_override():
    assert parse_search_query("Data Analyst Toronto") == SearchQuery("Data Analyst", "Toronto")
    assert parse_search_query("Python Engineer in Vancouver") == SearchQuery(
        "Python Engineer", "Vancouver"
    )
    assert parse_search_query("Data Analyst Toronto", location_override="Remote") == SearchQuery(
        "Data Analyst Toronto", "Remote"
    )


def test_greenhouse_normalization_filtering_and_html_cleanup():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs"):
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "title": "Data Analyst",
                            "location": {"name": "Toronto, Canada"},
                            "absolute_url": "https://example.com/jobs/1?source=test",
                            "updated_at": "2026-07-01T12:00:00Z",
                            "content": "&lt;p&gt;Analyze data with Python.&lt;/p&gt;",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"name": "Example Co"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_jobs(
            ["https://boards.greenhouse.io/example"],
            keywords="data Python",
            location="Toronto",
            client=client,
        )

    assert len(result.jobs) == 1
    assert result.jobs[0].company == "Example Co"
    assert result.jobs[0].job_description == "Analyze data with Python."
    assert result.jobs[0].source == "Greenhouse"


def test_concurrent_fetching_respects_worker_limit_and_reports_progress():
    lock = threading.Lock()
    active = 0
    max_active = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, max_active
        identifier = request.url.path.rsplit("/", 1)[-1]
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return httpx.Response(200, json=[lever_job(identifier)])

    entries = [lever_entry(f"company-{index}") for index in range(6)]
    progress = []
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_job_boards(
            entries,
            SearchQuery("Data Analyst", "Remote"),
            max_workers=3,
            retries=0,
            client=client,
            cache=TTLCache(ttl_seconds=60),
            progress_callback=lambda checked, total: progress.append((checked, total)),
        )

    assert 2 <= max_active <= 3
    assert result.companies_checked == 6
    assert progress[-1] == (6, 6)
    assert len(result.jobs) == 6


def test_partial_failure_is_retried_and_does_not_stop_other_companies():
    attempts = {"bad": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        identifier = request.url.path.rsplit("/", 1)[-1]
        if identifier == "bad":
            attempts["bad"] += 1
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json=[lever_job(identifier)])

    entries = [lever_entry("good"), lever_entry("bad")]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_job_boards(
            entries,
            SearchQuery("Data", "Remote"),
            max_workers=2,
            retries=1,
            client=client,
            cache=TTLCache(ttl_seconds=60),
            sleep=lambda _seconds: None,
        )

    assert attempts["bad"] == 2
    assert len(result.jobs) == 1
    assert result.companies_checked == 2
    assert result.warnings == ["Bad (Lever) is temporarily unavailable."]


def test_filtering_relevance_sorting_remote_and_deduplication():
    jobs = [
        JobPosting(
            "A",
            "Data Analyst",
            "Remote - Canada",
            "https://example.com/1",
            "Lever",
            "2026-01-01T00:00:00Z",
            "Python SQL",
        ),
        JobPosting(
            "B",
            "Operations Specialist",
            "Remote",
            "https://example.com/2",
            "Greenhouse",
            "2026-07-01T00:00:00Z",
            "Data analyst work using Python SQL",
        ),
        JobPosting(
            "A",
            "Data Analyst",
            "Remote - Canada",
            "https://example.com/1?duplicate=true",
            "Lever",
            "2026-08-01T00:00:00Z",
            "Python SQL",
        ),
        JobPosting(
            "C",
            "Data Analyst",
            "Toronto",
            "https://example.com/3",
            "Greenhouse",
            "2026-08-01T00:00:00Z",
            "Python SQL",
        ),
    ]
    result = filter_rank_dedupe(jobs, SearchQuery("Data Analyst", "Remote"))
    assert [job.company for job in result] == ["A", "B"]


def test_board_response_cache_avoids_repeated_http_calls():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[lever_job("cached")])

    cache = TTLCache(ttl_seconds=60)
    entry = lever_entry("cached")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = search_job_boards(
            [entry], SearchQuery("Data", "Remote"), client=client, cache=cache
        )
        second = search_job_boards(
            [entry], SearchQuery("Data", "Remote"), client=client, cache=cache
        )

    assert calls == 1
    assert first.jobs == second.jobs


def test_unsupported_board_is_reported_without_crashing():
    with httpx.Client() as client:
        result = search_jobs(["https://www.linkedin.com/jobs"], client=client)
    assert not result.jobs
    assert "Greenhouse" in result.warnings[0]


def test_parse_board_urls():
    assert parse_board_url("https://boards.greenhouse.io/acme").token == "acme"
    assert parse_board_url("https://jobs.lever.co/acme").api_host == "api.lever.co"
