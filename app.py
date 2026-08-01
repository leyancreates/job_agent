"""Streamlit UI for previewing and applying resume edits."""

import logging

import streamlit as st

from doc_utils import extract_doc_id
from google_docs_editor import apply_tailoring, preview_tailoring
from google_docs_reader import ConfigurationError, read_google_doc

logger = logging.getLogger(__name__)


def show_operation_error(action: str, exc: Exception) -> None:
    """Show safe configuration feedback while keeping diagnostics in Cloud logs."""
    logger.exception("Failed to %s", action)
    if isinstance(exc, ConfigurationError):
        st.error(str(exc))
    else:
        st.error(f"Could not {action}. Check the app logs or contact the app owner.")


st.title("AI Resume Tailor Agent")
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
