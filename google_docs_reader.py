"""Google Docs authentication, reading, and export helpers."""

from __future__ import annotations

import os
import json
from io import BytesIO
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.readonly",
]


class ConfigurationError(RuntimeError):
    """Raised when required deployment configuration is missing or invalid."""


def _credential_paths() -> tuple[Path | None, Path]:
    client_secret_value = os.getenv("GOOGLE_CLIENT_SECRET_FILE")
    client_secret = Path(client_secret_value) if client_secret_value else None
    token_file = Path(os.getenv("GOOGLE_TOKEN_FILE", "token.json"))
    return client_secret, token_file


def _service_account_credentials():
    raw_credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw_credentials:
        return None
    try:
        account_info = json.loads(raw_credentials)
        return ServiceAccountCredentials.from_service_account_info(account_info, scopes=SCOPES)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise ConfigurationError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid service-account JSON.") from exc


def _desktop_credentials():
    client_secret, token_file = _credential_paths()
    credentials = None

    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        if client_secret is None or not client_secret.exists():
            raise ConfigurationError(
                "Google authentication is not configured. Set GOOGLE_SERVICE_ACCOUNT_JSON "
                "for deployment or GOOGLE_CLIENT_SECRET_FILE for local development."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
        credentials = flow.run_local_server(port=0)

    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def get_google_services():
    """Return authenticated services using cloud credentials or local OAuth."""
    credentials = _service_account_credentials() or _desktop_credentials()
    docs = build("docs", "v1", credentials=credentials, cache_discovery=False)
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return docs, drive


def read_google_doc(doc_id: str) -> str:
    docs_service, _ = get_google_services()
    doc = docs_service.documents().get(documentId=doc_id).execute()
    parts: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        for run in element.get("paragraph", {}).get("elements", []):
            text_run = run.get("textRun")
            if text_run:
                parts.append(text_run.get("content", ""))
    return "".join(parts)


def export_google_doc_as_docx(doc_id: str, output_path: str = "google_resume.docx") -> str:
    _, drive_service = get_google_services()
    request = drive_service.files().export_media(
        fileId=doc_id,
        mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    file_data = BytesIO()
    downloader = MediaIoBaseDownload(file_data, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    Path(output_path).write_bytes(file_data.getvalue())
    return output_path
