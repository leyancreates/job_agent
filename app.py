"""Streamlit UI for previewing and applying resume edits."""

import logging
import csv
import io
from collections import Counter

import streamlit as st

from doc_utils import extract_doc_id
from google_docs_editor import apply_tailoring, preview_tailoring
from google_docs_reader import ConfigurationError, read_google_doc
from jobs import (
    CATEGORIES,
    JobPosting,
    entry_from_url,
    load_registry,
    parse_search_query,
    search_job_boards,
)
from matching.models import JobMatch
from matching.service import MatchAnalysisError, analyze_job_matches

logger = logging.getLogger(__name__)

ALL_CATEGORIES = "All categories"
SEARCH_PRESETS = {
    "Custom": ("", ALL_CATEGORIES),
    "Data & Analytics": ("Data Analyst", ALL_CATEGORIES),
    "Education": ("education", "education"),
    "Arts & Animation": ("animation", "arts/design"),
    "Design": ("design", "arts/design"),
    "Public Sector": ("", "public sector"),
}


def show_operation_error(action: str, exc: Exception) -> None:
    """Show safe configuration feedback while keeping diagnostics in Cloud logs."""
    logger.exception("Failed to %s", action)
    if isinstance(exc, ConfigurationError):
        st.error(str(exc))
    else:
        st.error(f"Could not {action}. Check the app logs or contact the app owner.")


st.set_page_config(page_title="AI Job Search Agent", layout="wide")
st.title("AI Job Search Agent")
st.caption(
    "Tailor a resume, discover public jobs, save opportunities, and compare resume fit. "
    "No automatic applications."
)

pending_tailor_job = st.session_state.pop("pending_tailor_job", None)
if pending_tailor_job:
    st.session_state["tailor_job_description"] = pending_tailor_job["description"]
    st.session_state["tailor_job_notice"] = (
        f"Loaded {pending_tailor_job['title']} at {pending_tailor_job['company']} "
        "from Match Analysis. Review it before generating edits."
    )

resume_tab, finder_tab, saved_tab, match_tab = st.tabs(
    ["Resume Tailor", "Job Finder", "Saved Jobs", "Match Analysis"]
)

with resume_tab:
    st.header("Resume Tailor")
    st.write("Preview truthful, job-specific resume edits before applying them to Google Docs.")

    google_doc_link = st.text_input("Google Docs Resume Link", key="google_doc_link")
    tailor_notice = st.session_state.get("tailor_job_notice")
    if tailor_notice:
        st.info(tailor_notice)
    job_description = st.text_area(
        "Job Description", height=220, key="tailor_job_description"
    )
    doc_id = extract_doc_id(google_doc_link)

    if st.button("Load resume"):
        if not doc_id:
            st.error("Please enter a valid Google Docs link.")
        else:
            try:
                with st.spinner("Reading Google Docs..."):
                    resume_text = read_google_doc(doc_id)
                if not resume_text.strip():
                    st.warning("This Google Doc does not contain readable resume text.")
                else:
                    st.session_state["resume_text"] = resume_text
                    st.session_state["resume_doc_id"] = doc_id
                    st.success("Resume loaded for tailoring and match analysis.")
            except Exception as exc:
                show_operation_error("read the document", exc)

    if "resume_text" in st.session_state:
        st.caption(
            f"Resume ready for match analysis · {len(st.session_state['resume_text']):,} characters"
        )
        st.text_area(
            "Resume preview",
            value=st.session_state["resume_text"],
            height=300,
            disabled=True,
        )

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


def job_table_rows(jobs: list[JobPosting]) -> list[dict[str, str | int | None]]:
    return [
        {
            "company": job.company,
            "title": job.title,
            "location": job.location,
            "job URL": job.job_url,
            "source": job.source,
            "posted date": job.posted_date,
            "relevance": job.relevance_score,
            "matched terms": ", ".join(job.matched_terms),
            "match type": job.match_type,
            "job description": job.job_description[:240],
        }
        for job in jobs
    ]


def selected_jobs(event, jobs: list[JobPosting]) -> list[JobPosting]:
    rows = getattr(getattr(event, "selection", None), "rows", [])
    return [jobs[index] for index in rows if 0 <= index < len(jobs)]


def analyze_selection(jobs: list[JobPosting]) -> None:
    if not jobs:
        st.warning("Select at least one job to analyze.")
        return
    resume_text = st.session_state.get("resume_text", "")
    if not resume_text.strip():
        st.warning("Load your resume in Resume Tailor before analyzing matches.")
        return
    try:
        with st.spinner(f"Analyzing {len(jobs)} selected job(s)..."):
            st.session_state["match_results"] = analyze_job_matches(resume_text, jobs)
        st.success("Match analysis is ready in the Match Analysis tab.")
    except MatchAnalysisError as exc:
        logger.warning("Match analysis failed", exc_info=True)
        st.error(str(exc))
    except Exception:
        logger.exception("Unexpected match analysis failure")
        st.error("Could not analyze these jobs. Check the app logs or contact the app owner.")


def show_list(items: tuple[str, ...], empty_message: str) -> None:
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        st.markdown(f"- {item}")


def show_match(match: JobMatch, index: int) -> None:
    job = match.job
    result = match.result
    st.subheader(f"{job.title} · {job.company}")
    score_column, recommendation_column = st.columns([1, 2])
    score_column.metric("Overall match", f"{result.overall_score}/100")
    recommendation_column.metric("Recommendation", result.recommendation)
    st.progress(result.overall_score / 100)

    skills_column, experience_column, education_column = st.columns(3)
    skills_column.metric("Skills", result.skills_score)
    experience_column.metric("Experience", result.experience_score)
    education_column.metric("Education / domain", result.education_domain_score)

    compatibility = result.location_work_authorization
    if compatibility is not None:
        st.info(
            f"Location / work authorization — {compatibility.status}: "
            f"{compatibility.explanation}"
        )

    with st.expander("Strengths, gaps, concerns, and explanation", expanded=index == 0):
        st.markdown("**Matched strengths**")
        show_list(result.matched_strengths, "No explicit strengths were identified.")
        st.markdown("**Missing, weak, or unknown qualifications**")
        show_list(
            result.missing_or_weak_qualifications,
            "No material gaps were identified from the supplied text.",
        )
        st.markdown("**Factual concerns**")
        show_list(result.factual_concerns, "No factual concerns were identified.")
        st.markdown("**Explanation**")
        st.write(result.explanation)

    if job.job_url:
        st.link_button("Open job posting", job.job_url)
    if st.button(
        "Use this job in Resume Tailor",
        key=f"use_match_for_tailoring_{index}_{result.job_id}",
    ):
        st.session_state["pending_tailor_job"] = {
            "company": job.company,
            "title": job.title,
            "description": job.job_description,
        }
        st.rerun()


with finder_tab:
    st.header("Job Finder")
    registry = load_registry()
    st.write(
        f"Search {len(registry)} maintained public Greenhouse, Lever, SmartRecruiters, "
        "and Ashby boards. "
        "LinkedIn and Indeed are intentionally excluded."
    )
    coverage = Counter(entry.category for entry in registry)
    with st.expander("Registry coverage by category"):
        st.dataframe(
            [
                {"category": category, "companies": count}
                for category, count in sorted(coverage.items())
            ],
            hide_index=True,
            width="stretch",
        )

    selected_preset = st.selectbox(
        "Search preset", list(SEARCH_PRESETS), key="job_search_preset"
    )
    if st.session_state.get("applied_job_search_preset") != selected_preset:
        preset_query, preset_category = SEARCH_PRESETS[selected_preset]
        st.session_state["job_search_query"] = preset_query
        st.session_state["job_category_filter"] = preset_category
        st.session_state["applied_job_search_preset"] = selected_preset

    search_mode = st.radio(
        "Search mode",
        ["Search all configured companies", "Search one company URL"],
        horizontal=True,
    )
    query_text = st.text_input(
        "Search query", placeholder="Animation Toronto", key="job_search_query"
    )
    category_filter = st.selectbox(
        "Industry / category",
        [ALL_CATEGORIES, *sorted(CATEGORIES)],
        key="job_category_filter",
        disabled=search_mode == "Search one company URL",
    )
    location_mode = st.selectbox(
        "Location handling", ["Auto-detect from query", "Remote", "Custom location"]
    )
    custom_location = (
        st.text_input("Custom location", placeholder="Toronto")
        if location_mode == "Custom location"
        else ""
    )
    company_url = ""
    if search_mode == "Search one company URL":
        company_url = st.text_input(
            "Company careers URL",
            placeholder="Public Greenhouse, Lever, SmartRecruiters, or Ashby careers URL",
        )

    location_override = "Remote" if location_mode == "Remote" else custom_location
    parsed_query = parse_search_query(query_text, location_override=location_override)
    if query_text.strip() or parsed_query.location:
        st.caption(
            f"Keywords: {parsed_query.keywords or 'Any'} · "
            f"Location: {parsed_query.location or 'Any'}"
        )

    if st.button("Find jobs", type="primary"):
        if (
            not query_text.strip()
            and not parsed_query.location
            and category_filter == ALL_CATEGORIES
        ):
            st.warning("Enter job keywords or a location, choose a category, or use a preset.")
        elif search_mode == "Search one company URL" and not company_url.strip():
            st.warning(
                "Enter a public Greenhouse, Lever, SmartRecruiters, or Ashby company URL."
            )
        else:
            try:
                if search_mode == "Search all configured companies":
                    entries = [
                        entry
                        for entry in registry
                        if category_filter == ALL_CATEGORIES
                        or entry.category == category_filter
                    ]
                else:
                    entries = [entry_from_url(company_url)]
                progress = st.progress(0, text=f"Checking 0 of {len(entries)} companies...")

                def update_progress(checked: int, total: int) -> None:
                    progress.progress(
                        checked / total,
                        text=f"Checked {checked} of {total} companies...",
                    )

                result = search_job_boards(
                    entries,
                    parsed_query,
                    max_workers=8,
                    progress_callback=update_progress,
                )
                progress.empty()
                st.session_state["job_results"] = result.jobs
                st.session_state["job_search_summary"] = (
                    result.companies_checked,
                    result.total_companies,
                    len(result.jobs),
                )
                st.session_state["job_search_warnings"] = result.warnings
                st.session_state["job_search_categories"] = result.categories_checked
            except ValueError as exc:
                st.warning(str(exc))

    jobs = st.session_state.get("job_results", [])
    summary = st.session_state.get("job_search_summary")
    if summary:
        checked, total, found = summary
        st.success(f"Checked {checked} of {total} companies and found {found} matching jobs.")
        categories_checked = st.session_state.get("job_search_categories", {})
        if categories_checked:
            category_summary = " · ".join(
                f"{category}: {count}"
                for category, count in sorted(categories_checked.items())
            )
            st.caption(f"Companies searched by category — {category_summary}")
    warnings = st.session_state.get("job_search_warnings", [])
    if warnings:
        with st.expander(f"Unavailable boards ({len(warnings)})"):
            for warning in warnings:
                st.warning(warning)
    if jobs:
        event = st.dataframe(
            job_table_rows(jobs),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            column_config={"job URL": st.column_config.LinkColumn("job URL")},
        )
        finder_selection = selected_jobs(event, jobs)
        save_column, analyze_column = st.columns(2)
        with save_column:
            if st.button("Save selected jobs", key="save_finder_jobs"):
                saved = {
                    job.dedupe_key: job for job in st.session_state.get("saved_jobs", [])
                }
                for job in finder_selection:
                    saved[job.dedupe_key] = job
                st.session_state["saved_jobs"] = list(saved.values())
                st.success(f"Saved {len(finder_selection)} selected job(s).")
        with analyze_column:
            if st.button("Analyze match", key="analyze_finder_jobs"):
                analyze_selection(finder_selection)
    elif "job_results" in st.session_state:
        st.info("No matching jobs were found.")


with saved_tab:
    st.header("Saved Jobs")
    saved_jobs = st.session_state.get("saved_jobs", [])
    if not saved_jobs:
        st.info("Select jobs in Job Finder and save them here for this session.")
    else:
        saved_event = st.dataframe(
            job_table_rows(saved_jobs),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            column_config={"job URL": st.column_config.LinkColumn("job URL")},
        )
        if st.button("Analyze match", key="analyze_saved_jobs"):
            analyze_selection(selected_jobs(saved_event, saved_jobs))
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


with match_tab:
    st.header("Resume Match Analysis")
    st.caption(
        "Scores are guidance based only on the supplied resume and job text; they are not "
        "hiring predictions. Missing information is treated as unknown, never as a positive match."
    )
    match_results = st.session_state.get("match_results", [])
    if not match_results:
        st.info(
            "Select up to 10 jobs in Job Finder or Saved Jobs, then choose Analyze match."
        )
    else:
        for match_index, match in enumerate(
            sorted(
                match_results,
                key=lambda item: item.result.overall_score,
                reverse=True,
            )
        ):
            show_match(match, match_index)
            if match_index < len(match_results) - 1:
                st.divider()
