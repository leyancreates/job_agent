import threading
import time

import httpx

from jobs.cache import TTLCache
from jobs.models import JobPosting
from jobs.query import SearchQuery, parse_search_query
from jobs.registry import CATEGORIES, SUPPORTED_PROVIDERS, BoardEntry, load_registry
from jobs.relevance import MIN_RELEVANCE_SCORE, expanded_terms
from jobs.service import (
    filter_rank_dedupe,
    relevance_score,
    search_job_boards,
    search_jobs,
)
from jobs.urls import parse_board_url


def lever_entry(
    identifier: str, company: str | None = None, category: str = "other"
) -> BoardEntry:
    return BoardEntry(
        company=company or identifier.title(),
        provider="lever",
        identifier=identifier,
        url=f"https://jobs.lever.co/{identifier}",
        verified_at="test",
        category=category,
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
    assert {entry.provider for entry in entries} == SUPPORTED_PROVIDERS
    assert {entry.category for entry in entries} == CATEGORIES
    assert all(entry.verified_at in {"2026-08-05", "2026-08-06"} for entry in entries)
    assert all(entry.category in CATEGORIES for entry in entries)
    assert all("linkedin" not in entry.url and "indeed" not in entry.url for entry in entries)

    companies = {entry.company for entry in entries}
    assert {
        "Columbia University",
        "University of Auckland",
        "Wake County Public Schools",
        "Stillwater Area Public Schools",
        "International Spy Museum",
        "Riot Games",
        "Wikimedia Foundation",
        "City and County of San Francisco",
        "Khan Academy",
    } <= companies


def test_registry_reports_company_counts_by_category():
    result = search_job_boards([], SearchQuery("", ""))
    assert result.categories_checked == {}

    entries = [
        lever_entry("education-one", category="education"),
        BoardEntry(
            "Museum",
            "lever",
            "museum",
            "https://jobs.lever.co/museum",
            "test",
            "arts/design",
        ),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        identifier = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=[lever_job(identifier)])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_job_boards(
            entries,
            SearchQuery("Data", "Remote"),
            client=client,
            cache=TTLCache(),
            retries=0,
        )
    assert result.categories_checked == {"education": 1, "arts/design": 1}


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
    assert result[0].relevance_score > result[1].relevance_score
    assert result[0].match_type == "title match"
    assert result[1].match_type == "description match"


def test_animation_toronto_rejects_unrelated_engineering_description_match():
    jobs = [
        JobPosting(
            "Software Co",
            "Software Engineer",
            "Toronto, Canada",
            "https://example.com/software",
            "Greenhouse",
            None,
            "Build rendering and animation infrastructure.",
        ),
        JobPosting(
            "Software Co",
            "Automation Engineer",
            "Toronto, Canada",
            "https://example.com/automation",
            "Greenhouse",
            None,
            "Build test infrastructure.",
        ),
        JobPosting(
            "Studio",
            "3D Animator",
            "Toronto, Canada",
            "https://example.com/animator",
            "Ashby",
            None,
            "Create character performances.",
        ),
        JobPosting(
            "Studio",
            "Motion Designer",
            "Montreal, Canada",
            "https://example.com/motion",
            "Ashby",
            None,
            "Create motion graphics.",
        ),
    ]

    result = filter_rank_dedupe(jobs, SearchQuery("Animation", "Toronto"))
    assert [job.title for job in result] == ["3D Animator"]
    assert result[0].relevance_score >= MIN_RELEVANCE_SCORE
    assert result[0].matched_terms == ("animation → animator",)
    assert result[0].match_type == "title match"


def test_teacher_toronto_requires_education_related_title_signal():
    jobs = [
        JobPosting(
            "Software Co",
            "Platform Engineer",
            "Toronto",
            "https://example.com/platform",
            "Lever",
            None,
            "Build tools used by teachers and schools.",
        ),
        JobPosting(
            "School",
            "Math Instructor",
            "Toronto",
            "https://example.com/instructor",
            "SmartRecruiters",
            None,
            "Teach secondary mathematics.",
        ),
    ]

    result = filter_rank_dedupe(jobs, SearchQuery("Teacher", "Toronto"))
    assert [job.title for job in result] == ["Math Instructor"]
    assert result[0].matched_terms == ("teacher → instructor",)


def test_synonym_expansion_and_title_weighting():
    assert {"animator", "motion designer", "character artist"} <= set(
        expanded_terms("animation")
    )
    assert {"teacher", "lecturer", "curriculum"} <= set(expanded_terms("education"))
    assert "ux designer" in expanded_terms("design")
    assert "museum" in expanded_terms("arts")

    exact = JobPosting(
        "A", "Animation Director", "Toronto", "https://a", "Ashby", None, ""
    )
    synonym = JobPosting(
        "B", "Character Artist", "Toronto", "https://b", "Greenhouse", None, ""
    )
    description_only = JobPosting(
        "C",
        "Software Engineer",
        "Toronto",
        "https://c",
        "Lever",
        None,
        "Supports the animation pipeline.",
    )
    query = SearchQuery("animation", "Toronto")
    assert relevance_score(exact, query) > relevance_score(synonym, query)
    assert relevance_score(synonym, query) > relevance_score(description_only, query)
    assert relevance_score(description_only, query) < MIN_RELEVANCE_SCORE
    assert filter_rank_dedupe([description_only], query) == []


def test_all_keywords_and_location_must_match():
    jobs = [
        JobPosting(
            "A",
            "Data Analyst",
            "Montreal",
            "https://a",
            "Greenhouse",
            None,
            "Python",
        ),
        JobPosting(
            "B",
            "Data Coordinator",
            "Toronto",
            "https://b",
            "Greenhouse",
            None,
            "Operations only.",
        ),
        JobPosting(
            "C",
            "Data Analyst",
            "Toronto",
            "https://c",
            "Greenhouse",
            None,
            "Python",
        ),
    ]
    result = filter_rank_dedupe(jobs, SearchQuery("Data Analyst", "Toronto"))
    assert [job.company for job in result] == ["C"]


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
    assert (
        parse_board_url("https://careers.smartrecruiters.com/Example").source
        == "SmartRecruiters"
    )
    assert parse_board_url("https://jobs.ashbyhq.com/example").source == "Ashby"
    assert (
        parse_board_url("https://example.wd1.myworkdayjobs.com/Careers").source
        == "Workday"
    )


def test_smartrecruiters_adapter_uses_public_list_and_detail_responses():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/postings"):
            return httpx.Response(
                200,
                json={
                    "totalFound": 1,
                    "content": [
                        {
                            "id": "teacher-1",
                            "name": "Visual Arts Teacher",
                            "company": {"name": "Example School", "identifier": "Example"},
                            "location": {"fullLocation": "Toronto, ON"},
                            "releasedDate": "2026-08-01T00:00:00Z",
                        }
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "teacher-1",
                "name": "Visual Arts Teacher",
                "company": {"name": "Example School", "identifier": "Example"},
                "location": {"fullLocation": "Toronto, ON"},
                "releasedDate": "2026-08-01T00:00:00Z",
                "postingUrl": "https://jobs.smartrecruiters.com/Example/teacher-1",
                "jobAd": {
                    "sections": {
                        "jobDescription": {"text": "<p>Teach visual arts.</p>"},
                        "qualifications": {"text": "<p>Teaching certificate.</p>"},
                    }
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_jobs(
            ["https://careers.smartrecruiters.com/Example"],
            keywords="teacher",
            location="Toronto",
            client=client,
        )

    assert len(result.jobs) == 1
    assert result.jobs[0].source == "SmartRecruiters"
    assert "Teach visual arts" in result.jobs[0].job_description
    assert result.jobs[0].job_url.startswith("https://jobs.smartrecruiters.com/")


def test_ashby_adapter_normalizes_public_postings_and_skips_unlisted_jobs():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apiVersion": "1",
                "jobs": [
                    {
                        "title": "Motion Designer",
                        "location": "Toronto",
                        "secondaryLocations": [{"location": "Remote - Canada"}],
                        "isRemote": True,
                        "isListed": True,
                        "descriptionPlain": "Create motion graphics and animation.",
                        "publishedAt": "2026-08-01T00:00:00Z",
                        "jobUrl": "https://jobs.ashbyhq.com/example/motion",
                    },
                    {
                        "title": "Hidden Animator",
                        "location": "Toronto",
                        "isListed": False,
                        "jobUrl": "https://jobs.ashbyhq.com/example/hidden",
                    },
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = search_jobs(
            ["https://jobs.ashbyhq.com/example"],
            keywords="animation",
            location="Remote",
            client=client,
        )

    assert [job.title for job in result.jobs] == ["Motion Designer"]
    assert result.jobs[0].source == "Ashby"


def test_workday_extension_point_does_not_scrape_or_crash():
    with httpx.Client(transport=httpx.MockTransport(lambda _request: None)) as client:
        result = search_jobs(
            ["https://example.wd1.myworkdayjobs.com/Careers"],
            keywords="teacher",
            client=client,
        )
    assert result.jobs == []
    assert result.warnings == [
        "example: Workday fetching is disabled until an employer exposes a documented, "
        "unauthenticated public jobs API."
    ]
