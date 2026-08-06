"""Streamlit UI for previewing and applying resume edits."""

import logging
import csv
import io
import os

import streamlit as st

from doc_utils import extract_doc_id
from google_docs_editor import apply_tailoring, preview_tailoring
from google_docs_reader import ConfigurationError, read_google_doc
from jobs import JobPosting, search_jobs

logger = logging.getLogger(__name__)


def show_operation_error(action: str, exc: Exception) -> None:
    """Show safe configuration feedback while keeping diagnostics in Cloud logs."""
    logger.exception("Failed to %s", action)
    if isinstance(exc, ConfigurationError):
        st.error(str(exc))
    else:
        st.error(f"Could not {action}. Check the app logs or contact the app owner.")


st.set_page_config(page_title="AI Job Search Agent", layout="wide")
st.title("AI Job Search Agent")
st.caption("Phase 1: tailor a resume, discover public jobs, and save opportunities. No automatic applications.")

resume_tab, finder_tab, saved_tab = st.tabs(["Resume Tailor", "Job Finder", "Saved Jobs"])

with resume_tab:
    st.header("Resume Tailor")
    st.write("Preview truthful, job-specific resume edits before applying them to Google Docs.")

    google_doc_link = st.text_input("Google Docs Resume Link")
    job_description = st.text_area("Job Description", height=220)
    doc_id = extract_doc_id(google_doc_link)

    if st.button("Load resume"):
        if not doc_id:
            st.error("Please enter a valid Google Docs link.")
        else:
            try:
                with st.spinner("Reading Google Docs..."):
                    st.session_state["resume_text"] = read_google_doc(doc_id)
                st.success("Resume loaded.")
            except Exception as exc:
                show_operation_error("read the document", exc)

    if "resume_text" in st.session_state:
        st.text_area("Resume preview", value=st.session_state["resume_text"], height=300, disabled=True)

    if st.button("Generate edit preview"):
        if not doc_id or not job_description.strip():
            st.warning("Add a valid Google Docs link and job description first.")
        else:
            try:
                with st.spinner("Preparing suggestions..."):
                    bullets, improved = preview_tailoring(doc_id, job_description)
                st.session_state["edit_preview"] = (doc_id, bullets, improved)
            except Exception as exc:
                show_operation_error("prepare suggestions", exc)

    preview = st.session_state.get("edit_preview")
    if preview:
        preview_doc_id, bullets, improved = preview
        if not bullets:
            st.info("No bullet points were found in this document.")
        else:
            st.subheader("Review proposed changes")
            for index, (original, replacement) in enumerate(zip(bullets, improved), start=1):
                st.markdown(f"**{index}. Original** — {original.text}")
                st.markdown(f"**Proposed** — {replacement}")

            st.warning("Applying will update the original Google Doc. Review every change first.")
            if st.button("Apply reviewed changes", type="primary"):
                try:
                    count = apply_tailoring(preview_doc_id, bullets, improved)
                    st.success(f"Updated {count} bullet points.")
                    del st.session_state["edit_preview"]
                except Exception as exc:
                    show_operation_error("apply changes", exc)


def job_table_rows(jobs: list[JobPosting]) -> list[dict[str, str | None]]:
    return [
        {
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "job URL": job.job_url,
            "source": job.source,
            "posted date": job.posted_date,
            "job description": job.job_description[:240],
        }
        for job in jobs
    ]


with finder_tab:
    st.header("Job Finder")
    st.write("Search public Greenhouse and Lever boards. LinkedIn and Indeed are intentionally excluded.")
    keywords = st.text_input("Job keywords", placeholder="data analyst Python")
    location = st.text_input("Location", placeholder="Toronto or Remote")
    company_url = st.text_input(
        "Company careers URL (optional)",
        placeholder="https://boards.greenhouse.io/company or https://jobs.lever.co/company",
    )

    if st.button("Find jobs", type="primary"):
        configured_urls = [url.strip() for url in os.getenv("JOB_BOARD_URLS", "").split(",") if url.strip()]
        board_urls = configured_urls + ([company_url] if company_url.strip() else [])
        if not board_urls:
            st.warning("Enter a Greenhouse or Lever careers URL, or configure JOB_BOARD_URLS.")
        else:
            with st.spinner("Collecting public job postings..."):
                result = search_jobs(board_urls, keywords=keywords, location=location)
            st.session_state["job_results"] = result.jobs
            for warning in result.warnings:
                st.warning(warning)

    jobs = st.session_state.get("job_results", [])
    if jobs:
        event = st.dataframe(
            job_table_rows(jobs),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            column_config={"job URL": st.column_config.LinkColumn("job URL")},
        )
        if st.button("Save selected jobs"):
            selected_rows = event.selection.rows
            saved = {job.dedupe_key: job for job in st.session_state.get("saved_jobs", [])}
            for row_index in selected_rows:
                saved[jobs[row_index].dedupe_key] = jobs[row_index]
            st.session_state["saved_jobs"] = list(saved.values())
            st.success(f"Saved {len(selected_rows)} selected job(s).")
    elif "job_results" in st.session_state:
        st.info("No matching jobs were found.")


with saved_tab:
    st.header("Saved Jobs")
    saved_jobs = st.session_state.get("saved_jobs", [])
    if not saved_jobs:
        st.info("Select jobs in Job Finder and save them here for this session.")
    else:
        st.dataframe(
            job_table_rows(saved_jobs),
            hide_index=True,
            width="stretch",
            column_config={"job URL": st.column_config.LinkColumn("job URL")},
        )
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(saved_jobs[0].to_dict()))
        writer.writeheader()
        writer.writerows(job.to_dict() for job in saved_jobs)
        st.download_button(
            "Download saved jobs as CSV",
            data=buffer.getvalue(),
            file_name="saved_jobs.csv",
            mime="text/csv",
        )
