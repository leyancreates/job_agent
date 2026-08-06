"""Small text normalization helpers."""

from html import unescape
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def html_to_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(value or ""))
    return " ".join(parser.parts)

