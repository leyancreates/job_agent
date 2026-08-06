import os
import subprocess
import sys
from pathlib import Path

from doc_utils import extract_doc_id
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
