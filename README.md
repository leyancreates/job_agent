# AI Job Search Agent

A modular Python and Streamlit project for finding public jobs, saving opportunities, and tailoring a Google Docs resume. Phase 1 does not submit applications.

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
google_docs_reader.py     Google Docs authentication and reading
google_docs_editor.py     resume preview and confirmed write-back
tests/                    mocked HTTP and resume workflow tests
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

## Safety and behavior

- Never asks the model to invent experience, metrics, tools, or qualifications.
- Uses structured JSON output so the number of suggestions must match the original bullets.
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
4. In Google Cloud, enable the Google Docs API and Google Drive API, create an OAuth Desktop App, and download its JSON credentials as `client_secret.json`.
5. Run:

   ```bash
   streamlit run app.py
   ```

Set `GOOGLE_CLIENT_SECRET_FILE=client_secret.json`. The first Google Docs operation opens a browser consent flow; later runs reuse the ignored `token.json`. If OAuth scopes change, delete `token.json` and authorize again.

## Deploy to Streamlit Community Cloud

1. Create a Google Cloud service account, enable the Google Docs and Drive APIs, and download its JSON key once.
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
