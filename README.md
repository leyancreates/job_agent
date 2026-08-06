# AI Job Search Agent

A modular Python and Streamlit project for finding public jobs, saving opportunities, comparing resume fit, and tailoring a Google Docs resume. The app does not submit applications.

## Architecture

```text
app.py                    Streamlit tabs and presentation
jobs/
  boards.json             maintained registry of verified public company boards
  registry.py             registry loading and validation
  query.py                keyword and location parsing
  relevance.py            synonym expansion, minimum threshold, and title-first scoring
  cache.py                thread-safe 15-minute response cache
  models.py               normalized JobPosting model and match explanations
  urls.py                 supported public ATS URL parsing
  providers.py            common provider interface and safe Workday extension point
  greenhouse.py           Greenhouse Job Board API adapter
  lever.py                Lever Postings API adapter
  smartrecruiters.py       SmartRecruiters public Posting API adapter
  ashby.py                 Ashby public Job Postings API adapter
  service.py              concurrent fetch, retries, filtering, ranking, deduplication
  text.py                 safe HTML-to-text conversion
matching/
  models.py               validated scores, recommendations, and evidence fields
  cache.py                thread-safe six-hour match-result cache
  service.py              batched Responses API calls and strict JSON Schema validation
google_docs_reader.py     Google Docs authentication and reading
google_docs_editor.py     resume preview and confirmed write-back
tests/                    mocked HTTP, OpenAI, Streamlit, and resume workflow tests
```

## Job Finder

- Enter one query such as `Animation Toronto`; the parser separates recognized locations from job keywords.
- Use a search preset for Data & Analytics, Education, Arts & Animation, Design, or Public Sector, then edit the generated query if needed.
- Optionally restrict the registry to technology, education, arts/design, public sector, nonprofit, healthcare, finance, other, or all categories.
- Choose **Search all configured companies** to search the maintained registry, or **Search one company URL** for a public Greenhouse, Lever, SmartRecruiters, or Ashby board.
- Use the Remote or custom-location controls when automatic parsing is not appropriate.
- Review each result's relevance score, matched query terms, and title/description match label.
- Select rows and save them for the current browser session.
- Download saved jobs as CSV for durable local storage.

The bundled registry contains 89 boards verified on 2026-08-05 and 2026-08-06: 70 Greenhouse, 4 Lever, 10 SmartRecruiters, and 5 Ashby organizations. It includes universities, public-school systems, a museum, game and animation studios, nonprofits, public-sector employers, healthcare organizations, and education technology companies. The app searches public APIs concurrently with at most eight workers. Each board receives a timeout and up to two retries; a failed company becomes a safe warning and does not stop the search. Successful responses are cached in memory for 15 minutes.

### Relevance and synonyms

A location match never satisfies the keyword requirement. Every non-empty keyword concept must match and the result must also satisfy the requested location. Title matches receive the dominant score; description matches are secondary evidence. Results below the minimum relevance score of 30 are discarded, which prevents a Toronto software role from passing an `Animation Toronto` search merely because its description mentions animation.

The maintained synonym groups include:

- `animation`: animator, 2D/3D animator, motion designer, motion graphics, character artist
- `education`: teacher, instructor, educator, lecturer, professor, tutor, curriculum, academic
- `design`: graphic, visual, UX, and creative designer
- `arts`: artist, gallery, museum, curator, arts coordinator

Exact query phrases rank above synonym and close-title matches, which rank above mixed title/description and description-only matches. Description-only results must contain enough multi-term evidence to clear the threshold. Scores describe search relevance, not resume fit or hiring probability.

### Search flow

1. Parse the query into keywords and location.
2. Load all registry entries or parse one user-supplied ATS URL.
3. Fetch public board APIs concurrently with bounded connections, timeouts, retries, and per-board failure isolation.
4. Normalize every posting into company, title, location, job URL, source, posted date, and description.
5. Expand supported role synonyms and require every query concept plus the requested, case-insensitive location.
6. Score exact/title matches above description evidence, reject results below the relevance threshold, and record matched terms and match type.
7. Deduplicate canonical URLs and sort by relevance, then the provider's public date field.

### Maintaining the registry

Edit `jobs/boards.json` to add or remove companies. Every entry must contain:

```json
{
  "company": "Example",
  "provider": "greenhouse",
  "identifier": "example",
  "url": "https://boards.greenhouse.io/example",
  "verified_at": "YYYY-MM-DD",
  "category": "technology"
}
```

`category` must be one of `technology`, `education`, `arts/design`, `public sector`, `nonprofit`, `healthcare`, `finance`, or `other`.

Before adding an entry, verify that its official public endpoint returns HTTP 200 and a valid jobs collection:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{identifier}/jobs`
- Lever: `https://api.lever.co/v0/postings/{identifier}?mode=json`
- SmartRecruiters: `https://api.smartrecruiters.com/v1/companies/{identifier}/postings`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{identifier}`

Run `pytest tests/test_jobs.py` after every registry change. Tests enforce at least 50 unique entries, supported providers, URL/identifier agreement, and verification metadata.

### Limitations

- The registry is maintained source data, not an exhaustive global jobs index. Companies may change ATS providers or disable boards after the recorded verification date.
- Greenhouse exposes `updated_at`, which is used as the best available public date even though it may differ from the original posting date.
- Lever does not expose board-level company metadata, so registry names are maintained explicitly.
- SmartRecruiters list responses omit full descriptions. The adapter retrieves details only for title candidates, with a per-board safety cap, and falls back to public list metadata if one detail request fails.
- Workday deployments vary and there is no generic public API assumed by this project. `JobProviderAdapter` includes a disabled Workday extension point, but the app never bypasses access controls or scrapes authenticated/protected pages.
- Cache state and saved jobs are process/session scoped; download CSV before a Streamlit restart if durable storage is needed.
- LinkedIn, Indeed, Google Jobs, protected sites, and automatic application submission are intentionally out of scope.

## Resume Match Analysis

1. In **Resume Tailor**, load a Google Docs resume. Its plain text is kept in the current Streamlit session and the document is not modified during scoring.
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

- Match requests contain only resume text plus each job's company, title, location, and description. Job URLs, source metadata, and saved-job state are not sent.
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
