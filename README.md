# AI Job Search Agent

A modular Python and Streamlit project for finding public jobs, saving opportunities, comparing resume fit, and working with a Google Docs or uploaded resume. The app does not submit applications.

## Architecture

```text
app.py                    Streamlit tabs and presentation
jobs/
  boards.json             maintained registry of verified public company boards
  registry.py             registry loading and validation
  query.py                keyword and location parsing
  cache.py                thread-safe 15-minute response cache
  models.py               normalized JobPosting model
  urls.py                 Greenhouse and Lever URL parsing
  greenhouse.py           Greenhouse Job Board API adapter
  lever.py                Lever Postings API adapter
  service.py              concurrent fetch, retries, filtering, ranking, deduplication
  text.py                 safe HTML-to-text conversion
matching/
  models.py               validated scores, recommendations, and evidence fields
  cache.py                thread-safe six-hour match-result cache
  service.py              batched Responses API calls and strict JSON Schema validation
resumes/
  models.py               source-independent ResumeContent model
  parsers.py              PDF, DOCX, TXT, and Google Docs text normalization
  errors.py               safe upload and extraction errors
google_docs_reader.py     Google Docs authentication and reading
google_docs_editor.py     resume preview and confirmed write-back
tests/                    mocked HTTP, OpenAI, Streamlit, and resume workflow tests
```

## Job Finder

- Enter one query such as `Data Analyst Toronto`; the parser separates recognized locations from job keywords.
- Choose **Search all configured companies** to search the maintained registry, or **Search one company URL** for a public `boards.greenhouse.io/...` or `jobs.lever.co/...` board.
- Use the Remote or custom-location controls when automatic parsing is not appropriate.
- Select rows and save them for the current browser session.
- Download saved jobs as CSV for durable local storage.

The bundled registry currently contains 57 boards verified on 2026-08-05: 53 Greenhouse companies and 4 Lever companies. Greenhouse and Lever expose company-specific public APIs, so the app searches this registry concurrently with at most eight workers. Each board receives a timeout and up to two retries; a failed company becomes a safe warning and does not stop the search. Successful board responses are cached in memory for 15 minutes.

### Search flow

1. Parse the query into keywords and location.
2. Load all registry entries or parse one user-supplied ATS URL.
3. Fetch public board APIs concurrently with bounded connections, timeouts, retries, and per-board failure isolation.
4. Normalize every posting into company, title, location, job URL, source, posted date, and description.
5. Match all keyword tokens against title and description, apply a case-insensitive location filter, and deduplicate canonical URLs.
6. Sort by title-weighted relevance and then the provider's public date field.

### Maintaining the registry

Edit `jobs/boards.json` to add or remove companies. Every entry must contain:

```json
{
  "company": "Example",
  "provider": "greenhouse",
  "identifier": "example",
  "url": "https://boards.greenhouse.io/example",
  "verified_at": "YYYY-MM-DD"
}
```

Before adding an entry, verify that its official public endpoint returns HTTP 200 and a valid jobs collection:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{identifier}/jobs`
- Lever: `https://api.lever.co/v0/postings/{identifier}?mode=json`

Run `pytest tests/test_jobs.py` after every registry change. Tests enforce at least 50 unique entries, supported providers, URL/identifier agreement, and verification metadata.

### Limitations

- The registry is maintained source data, not an exhaustive global jobs index. Companies may change ATS providers or disable boards after the recorded verification date.
- Greenhouse exposes `updated_at`, which is used as the best available public date even though it may differ from the original posting date.
- Lever does not expose board-level company metadata, so registry names are maintained explicitly.
- Cache state and saved jobs are process/session scoped; download CSV before a Streamlit restart if durable storage is needed.
- LinkedIn, Indeed, Google Jobs, protected sites, and automatic application submission are intentionally out of scope.

## Resume sources

In **Resume Tailor**, choose one source:

- **Google Docs** keeps the existing link, preview, and confirmed write-back workflow.
- **Upload File** accepts PDF, DOCX, and UTF-8 TXT resumes. PDF text is extracted with `pdfplumber`, DOCX paragraphs and table cells with `python-docx`, and TXT directly as UTF-8.

Both sources create the same `ResumeContent` object and store its plain text in Streamlit session state. After loading, the UI shows a confirmation, filename, word count, and text preview. Match Analysis and future scoring features consume the same resume text regardless of source.

Uploaded files are read-only in this phase: the app extracts and analyzes their text but does not overwrite or export a modified PDF/DOCX. Switch to Google Docs when you want to preview and apply Resume Tailor edits. Empty, unsupported, corrupted, password-protected, or non-UTF-8 files produce safe user-facing messages.

Image-only or scanned PDFs require OCR, which is not included in this phase; they are reported as containing no readable text.

## Resume Match Analysis

1. In **Resume Tailor**, load a Google Docs resume or upload a PDF, DOCX, or UTF-8 TXT file. Its plain text is kept in the current Streamlit session and the source document is not modified during scoring.
2. Search or open Saved Jobs, select up to 10 rows, and choose **Analyze match**.
3. The app sends one batched Responses API request for selected jobs that are not already cached.
4. Open **Match Analysis** to compare overall, skills, experience, and education/domain scores. Expand each result for strengths, gaps, factual concerns, and a short explanation.
5. Choose **Use this job in Resume Tailor** to copy that job description into the existing preview workflow. The app never rewrites or applies resume edits automatically.

### Score interpretation

- **Strong match (75–100):** the supplied text contains substantial explicit evidence for the role.
- **Possible match (45–74):** there is useful alignment alongside material gaps or unknowns.
- **Low match (0–44):** the supplied text provides limited evidence for important requirements.

Scores are guidance for prioritizing review, not hiring predictions. Missing resume information is treated as unknown, not as a positive match. Location or work-authorization compatibility is shown only when the supplied resume and job text provide relevant evidence. The matcher does not infer protected or sensitive personal attributes.

### Privacy, cost, and caching

- Uploaded files are parsed inside the Streamlit process. Match requests contain only extracted resume text plus each job's company, title, location, and description. Job URLs, source metadata, saved-job state, and original file bytes are not sent.
- Responses API requests set `store=false`. Review your OpenAI organization settings and policies for any additional retention controls your deployment requires.
- At most 10 jobs are analyzed per batch. Resume input is capped at 30,000 characters and each job description at 16,000 characters to bound latency and token usage; unusually long documents may therefore receive incomplete coverage.
- Results are cached in memory for six hours using a SHA-256 hash of the resume, job details, and `OPENAI_MODEL`. Repeated Streamlit reruns reuse cached results, but cache state is lost when the process restarts.
- Actual cost and latency depend on the configured model, input length, number of uncached jobs, and current API pricing. Use an efficient model for routine screening and verify quality on representative resumes.

## Safety and behavior

- Never asks the model to invent experience, metrics, tools, or qualifications.
- Treats absent experience, education, certifications, and work authorization as unknown.
- Uses structured JSON output so the number of suggestions must match the original bullets.
- Uses a separate strict JSON Schema for batched resume match results and validates scores again in Python.
- Shows every proposed rewrite before changing the document.
- Uses a service account in Streamlit Community Cloud and cached OAuth locally.
- Reads secrets from environment variables; credentials are never committed.

## Setup

1. Create a Python 3.11+ virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Export `OPENAI_API_KEY`. Optionally override `OPENAI_MODEL`.
4. To use the Google Docs source, enable the Google Docs API and Google Drive API, create an OAuth Desktop App, and download its JSON credentials as `client_secret.json`. This is not required when using uploaded resumes only.
5. Run:

   ```bash
   streamlit run app.py
   ```

Set `GOOGLE_CLIENT_SECRET_FILE=client_secret.json`. The first Google Docs operation opens a browser consent flow; later runs reuse the ignored `token.json`. If OAuth scopes change, delete `token.json` and authorize again.

## Deploy to Streamlit Community Cloud

1. If the deployment will use Google Docs, create a Google Cloud service account, enable the Google Docs and Drive APIs, and download its JSON key once. Skip this and the next step for upload-only deployments.
2. Share each resume Google Doc with the service account's `client_email` as an editor. A service account cannot access a document merely because its URL is known.
3. Open [Streamlit Community Cloud](https://share.streamlit.io), choose this repository and branch, and set the entrypoint to `app.py`.
4. In **Advanced settings**, select Python 3.12 and paste these root-level secrets:

   ```toml
   OPENAI_API_KEY = "your-api-key"
   OPENAI_MODEL = "gpt-5.6-luna"
   GOOGLE_SERVICE_ACCOUNT_JSON = '''{"type":"service_account", "project_id":"...", "private_key":"...", "client_email":"..."}'''
   ```

   Paste the complete downloaded service-account JSON between the triple single quotes. Never add `.streamlit/secrets.toml`, the JSON key file, or API keys to Git.

5. Deploy. If startup fails, open **Manage app → Logs** and verify the dependency installation and secret names.

Community Cloud exposes root-level secrets as environment variables, which this app reads through `os.environ`. The repository-root `requirements.txt` is the only production dependency file.

## Development

```bash
pip install -r requirements-dev.txt
pytest
python -m compileall .
```

`test_edit_doc.py` is a non-writing manual smoke test. Provide a document through `TEST_GOOGLE_DOC_ID`; do not hard-code personal document IDs.

## Notes

The default model is `gpt-5.6-luna`, suitable for efficient, high-volume text work. Set `OPENAI_MODEL` to another model your API project can access if needed.
