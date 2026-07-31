from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from io import BytesIO

SCOPES = [
    "https://www.googleapis.com/auth/documents"
]

CLIENT_SECRET_FILE = "client_secret_953664265018-7ncqaf3kpk9guqrb9fq4j8pca1keq9da.apps.googleusercontent.com.json"

def get_google_services():
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        SCOPES
    )
    creds = flow.run_local_server(port=0, prompt="consent")

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    return docs_service, drive_service


def read_google_doc(doc_id):
    docs_service, _ = get_google_services()

    doc = docs_service.documents().get(documentId=doc_id).execute()
    content = doc.get("body", {}).get("content", [])

    text = ""

    for element in content:
        if "paragraph" in element:
            for run in element["paragraph"].get("elements", []):
                if "textRun" in run:
                    text += run["textRun"].get("content", "")

    return text


def export_google_doc_as_docx(doc_id, output_path="google_resume.docx"):
    _, drive_service = get_google_services()

    request = drive_service.files().export_media(
        fileId=doc_id,
        mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    file_data = BytesIO()
    downloader = MediaIoBaseDownload(file_data, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    with open(output_path, "wb") as f:
        f.write(file_data.getvalue())

    return output_path
