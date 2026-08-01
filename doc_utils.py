"""Pure helpers shared by the UI and tests."""

from urllib.parse import urlparse


def extract_doc_id(link: str) -> str:
    try:
        parts = urlparse(link.strip()).path.split("/")
        marker = parts.index("d")
        return parts[marker + 1] if parts[marker - 1] == "document" else ""
    except (ValueError, IndexError):
        return ""

