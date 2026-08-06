"""Load and validate the maintained public job-board registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jobs.urls import BoardReference, parse_board_url

REGISTRY_PATH = Path(__file__).with_name("boards.json")
SUPPORTED_PROVIDERS = {"greenhouse", "lever", "smartrecruiters", "ashby"}
CATEGORIES = {
    "technology",
    "education",
    "arts/design",
    "public sector",
    "nonprofit",
    "healthcare",
    "finance",
    "other",
}


@dataclass(frozen=True)
class BoardEntry:
    company: str
    provider: str
    identifier: str
    url: str
    verified_at: str
    category: str = "other"

    def board_reference(self) -> BoardReference:
        reference = parse_board_url(self.url)
        if reference.source.casefold() != self.provider or reference.token != self.identifier:
            raise ValueError(f"Registry entry does not match its URL: {self.company}")
        return reference


def load_registry(path: Path = REGISTRY_PATH) -> list[BoardEntry]:
    raw_entries = json.loads(path.read_text(encoding="utf-8"))
    entries = [BoardEntry(**raw) for raw in raw_entries]
    keys = {(entry.provider, entry.identifier) for entry in entries}
    if len(keys) != len(entries):
        raise ValueError("Job-board registry contains duplicate provider identifiers.")
    for entry in entries:
        if (
            entry.provider not in SUPPORTED_PROVIDERS
            or entry.category not in CATEGORIES
            or not entry.company.strip()
        ):
            raise ValueError(f"Invalid registry entry: {entry}")
        entry.board_reference()
    return entries


def entry_from_url(url: str) -> BoardEntry:
    reference = parse_board_url(url)
    return BoardEntry(
        company="",
        provider=reference.source.casefold(),
        identifier=reference.token,
        url=url.strip(),
        verified_at="user-supplied",
        category="other",
    )
