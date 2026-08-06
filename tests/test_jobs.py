import httpx

from jobs.service import search_jobs
from jobs.urls import parse_board_url


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


def test_lever_normalization_and_deduplication():
    payload = [
        {
            "text": "Python Engineer",
            "categories": {"location": "Remote"},
            "hostedUrl": "https://jobs.lever.co/example/abc",
            "createdAt": 1751328000000,
            "descriptionPlain": "Build Python services.",
        },
        {
            "text": "Python Engineer",
            "categories": {"location": "Remote"},
            "hostedUrl": "https://jobs.lever.co/example/abc?ref=duplicate",
            "createdAt": 1751328000000,
            "descriptionPlain": "Build Python services.",
        },
    ]

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        result = search_jobs(
            ["https://jobs.lever.co/example"], keywords="Python", client=client
        )

    assert len(result.jobs) == 1
    assert result.jobs[0].source == "Lever"
    assert result.jobs[0].posted_date.startswith("2025-07-01")


def test_unsupported_board_is_reported_without_crashing():
    with httpx.Client() as client:
        result = search_jobs(["https://www.linkedin.com/jobs"], client=client)
    warning = result.warnings[0]
    assert not result.jobs
    assert "Greenhouse" in warning


def test_parse_board_urls():
    assert parse_board_url("https://boards.greenhouse.io/acme").token == "acme"
    assert parse_board_url("https://jobs.lever.co/acme").api_host == "api.lever.co"
