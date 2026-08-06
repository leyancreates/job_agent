import os
import subprocess
import sys
from pathlib import Path

from doc_utils import extract_doc_id
from jobs.models import JobPosting
from matching.models import JobMatch, MatchResult
from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_extract_doc_id():
    assert extract_doc_id("https://docs.google.com/document/d/abc123/edit") == "abc123"


def test_extract_doc_id_rejects_invalid_link():
    assert extract_doc_id("https://example.com/not-a-doc") == ""


def test_streamlit_cloud_import_contract_in_fresh_process():
    """Import the entry point and public jobs API from the repository root."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import app
from jobs import (
    JobPosting,
    entry_from_url,
    load_registry,
    parse_search_query,
    search_job_boards,
)
assert JobPosting and entry_from_url and load_registry
assert parse_search_query and search_job_boards
""",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_streamlit_app_starts_without_exception():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
    app.run(timeout=20)
    assert not app.exception


def test_resume_source_switch_shows_only_upload_controls():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=20)
    app.radio[0].set_value("Upload File").run(timeout=20)

    assert not app.exception
    assert len(app.get("file_uploader")) == 1
    assert all(item.label != "Google Docs Resume Link" for item in app.text_input)


def test_match_analysis_result_renders_without_exception():
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"))
    app.session_state["match_results"] = [
        JobMatch(
            job=JobPosting(
                company="Example",
                title="Data Analyst",
                location="Toronto",
                job_url="https://example.com/job",
                source="Greenhouse",
                posted_date=None,
                job_description="Analyze data with Python.",
            ),
            result=MatchResult(
                job_id="example-job",
                overall_score=80,
                skills_score=85,
                experience_score=75,
                education_domain_score=70,
                location_work_authorization=None,
                matched_strengths=("Python is explicitly listed.",),
                missing_or_weak_qualifications=("Unknown: work authorization.",),
                factual_concerns=(),
                recommendation="Strong match",
                explanation="Explicit skills align with the role.",
            ),
        )
    ]
    app.run(timeout=20)
    assert not app.exception
    assert any(metric.value == "80/100" for metric in app.metric)
