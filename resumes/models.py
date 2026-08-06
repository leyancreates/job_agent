"""A source-independent resume representation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResumeContent:
    text: str
    source: str
    filename: str
    google_doc_id: str | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split())
