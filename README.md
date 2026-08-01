# AI Resume Tailor Agent

A Python and Streamlit tool that reads a Google Docs resume, proposes truthful job-specific bullet rewrites, and applies them only after review.

## Safety and behavior

- Never asks the model to invent experience, metrics, tools, or qualifications.
- Uses structured JSON output so the number of suggestions must match the original bullets.
- Shows every proposed rewrite before changing the document.
- Stores Google OAuth tokens locally in ignored `token.json`.
- Reads secrets from environment variables; credentials are never committed.

## Setup

1. Create a Python 3.11+ virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Optionally override `OPENAI_MODEL`.
4. In Google Cloud, enable the Google Docs API and Google Drive API, create an OAuth Desktop App, and download its JSON credentials as `client_secret.json`.
5. Run:

   ```bash
   streamlit run app.py
   ```

The first Google Docs operation opens a browser consent flow. Later runs reuse `token.json`. If OAuth scopes change, delete `token.json` and authorize again.

## Development

```bash
pip install -r requirements-dev.txt
pytest
python -m compileall .
```

`test_edit_doc.py` is a non-writing manual smoke test. Provide a document through `TEST_GOOGLE_DOC_ID`; do not hard-code personal document IDs.

## Notes

The default model is `gpt-5.6-luna`, suitable for efficient, high-volume text work. Set `OPENAI_MODEL` to another model your API project can access if needed.

