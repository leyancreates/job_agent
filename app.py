
import streamlit as st
from google_docs_reader import read_google_doc
from google_docs_editor import tailor_google_doc

st.title("AI Resume Tailor Agent")

st.write("Paste a Google Docs resume link and a job description. The agent will improve bullet points directly inside Google Docs while keeping the original format.")

def extract_doc_id(link):
    if "/document/d/" in link:
        return link.split("/document/d/")[1].split("/")[0]
    return ""

google_doc_link = st.text_input("Google Docs Resume Link")

job_description = st.text_area(
    "Job Description",
    height=220,
    placeholder="Paste the job description here..."
)

doc_id = extract_doc_id(google_doc_link)

if st.button("Preview Resume from Google Docs"):
    if not doc_id:
        st.error("Please enter a valid Google Docs link.")
    else:
        with st.spinner("Reading Google Docs..."):
            try:
                resume_text = read_google_doc(doc_id)
                st.session_state["resume_text"] = resume_text
                st.success("Resume loaded successfully.")
            except Exception as e:
                st.error(f"Error reading Google Docs: {e}")

if "resume_text" in st.session_state:
    st.subheader("Resume Preview")
    st.text_area(
        "Loaded Resume",
        value=st.session_state["resume_text"],
        height=300
    )

if st.button("Tailor Google Docs Resume"):
    if not doc_id:
        st.error("Please enter a valid Google Docs link.")
    elif not job_description:
        st.warning("Please paste a job description.")
    else:
        with st.spinner("AI is tailoring your Google Docs resume..."):
            try:
                result = tailor_google_doc(doc_id, job_description)
                st.success(result)
                st.info("Open or refresh your Google Docs file to see the updated bullet points.")
            except Exception as e:
                st.error(f"Error tailoring resume: {e}")
