# AI Job Search Agent

A modular Python and Streamlit project for finding public jobs, saving opportunities, and tailoring a Google Docs resume. Phase 1 does not submit applications.

## Architecture

```text
app.py                    Streamlit tabs and presentation
jobs/
  models.py               normalized JobPosting model
  urls.py                 Greenhouse and Lever URL parsing
  greenhouse.py           Greenhouse Job Board API adapter
  lever.py                Lever Postings API adapter
  service.py              collection, filtering, warnings, deduplication
  text.py                 safe HTML-to-text conversion
google_docs_reader.py     Google Docs authentication and reading
google_docs_editor.py     resume preview and confirmed write-back
tests/                    mocked HTTP and resume workflow tests
```

## Job Finder

- Enter keywords and a location.
- Optionally paste a public `boards.greenhouse.io/...` or `jobs.lever.co/...` company board URL.
- Select rows and save them for the current browser session.
- Download saved jobs as CSV for durable local storage.

Greenhouse and Lever expose company-specific public APIs, not a global search endpoint. To search a maintained set of boards when no URL is entered, configure a comma-separated `JOB_BOARD_URLS` environment variable. LinkedIn, Indeed, and automatic application submission are intentionally out of scope.

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
   JOB_BOARD_URLS = "https://boards.greenhouse.io/company,https://jobs.lever.co/company"
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
