"""Synonym-aware, title-first job relevance scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from jobs.models import JobPosting
from jobs.query import SearchQuery

MIN_RELEVANCE_SCORE = 30

SYNONYM_GROUPS: dict[str, tuple[str, ...]] = {
    "animation": (
        "animation",
        "animator",
        "2d animator",
        "3d animator",
        "motion designer",
        "motion graphics",
        "character artist",
    ),
    "education": (
        "education",
        "teacher",
        "instructor",
        "educator",
        "lecturer",
        "professor",
        "tutor",
        "curriculum",
        "academic",
    ),
    "design": (
        "design",
        "graphic designer",
        "visual designer",
        "ux designer",
        "creative designer",
    ),
    "arts": (
        "arts",
        "artist",
        "gallery",
        "museum",
        "curator",
        "arts coordinator",
    ),
}


@dataclass(frozen=True)
class _Concept:
    label: str
    alternatives: tuple[str, ...]


@dataclass(frozen=True)
class RelevanceMatch:
    score: int
    matched_terms: tuple[str, ...]
    match_type: str | None
    all_terms_matched: bool


def normalize_search_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#]+", value.casefold()))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = normalize_search_text(phrase)
    return bool(normalized_phrase) and f" {normalized_phrase} " in f" {text} "


def _phrase_indexes(tokens: list[str], phrase: str) -> set[int]:
    parts = normalize_search_text(phrase).split()
    if not parts or len(parts) > len(tokens):
        return set()
    indexes: set[int] = set()
    for start in range(len(tokens) - len(parts) + 1):
        if tokens[start : start + len(parts)] == parts:
            indexes.update(range(start, start + len(parts)))
    return indexes


def query_concepts(keywords: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return stable query concepts and their accepted title/description alternatives."""
    tokens = normalize_search_text(keywords).split()
    claimed: set[int] = set()
    concepts: list[_Concept] = []

    for label, alternatives in SYNONYM_GROUPS.items():
        matched_indexes: set[int] = set()
        matched_aliases: list[str] = []
        for alias in sorted(alternatives, key=lambda item: len(item.split()), reverse=True):
            indexes = _phrase_indexes(tokens, alias)
            if indexes:
                matched_indexes.update(indexes)
                matched_aliases.append(alias)
        if matched_aliases:
            claimed.update(matched_indexes)
            query_label = max(matched_aliases, key=lambda item: len(item.split()))
            concepts.append(_Concept(query_label, alternatives))

    for index, token in enumerate(tokens):
        if index not in claimed:
            concepts.append(_Concept(token, (token,)))

    return tuple((concept.label, concept.alternatives) for concept in concepts)


def expanded_terms(keywords: str) -> tuple[str, ...]:
    terms: list[str] = []
    for _label, alternatives in query_concepts(keywords):
        for alternative in alternatives:
            if alternative not in terms:
                terms.append(alternative)
    return tuple(terms)


def _close_title_match(label: str, title: str) -> str | None:
    label_tokens = normalize_search_text(label).split()
    title_tokens = normalize_search_text(title).split()
    if not label_tokens or not title_tokens:
        return None
    width = len(label_tokens)
    candidates = [
        " ".join(title_tokens[start : start + width])
        for start in range(max(1, len(title_tokens) - width + 1))
    ]
    candidates = [
        candidate
        for candidate in candidates
        if (prefix_width := min(5, len(label), len(candidate))) >= 3
        and candidate[:prefix_width] == label[:prefix_width]
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda item: SequenceMatcher(None, label, item).ratio())
    if SequenceMatcher(None, label, best).ratio() >= 0.82:
        return best
    return None


def evaluate_relevance(job: JobPosting, query: SearchQuery) -> RelevanceMatch:
    concepts = query_concepts(query.keywords)
    if not concepts:
        return RelevanceMatch(0, (), None, True)

    title = normalize_search_text(job.title)
    description = normalize_search_text(job.job_description)
    title_matches = 0
    description_matches = 0
    matched_terms: list[str] = []
    all_terms_matched = True
    score = 0

    for label, alternatives in concepts:
        title_term = next(
            (term for term in alternatives if _contains_phrase(title, term)), None
        )
        if title_term:
            title_matches += 1
            score += 35
            matched_terms.append(
                label if normalize_search_text(label) == normalize_search_text(title_term)
                else f"{label} → {title_term}"
            )
            continue

        close_term = _close_title_match(label, title)
        if close_term:
            title_matches += 1
            score += 30
            matched_terms.append(f"{label} ≈ {close_term}")
            continue

        description_term = next(
            (term for term in alternatives if _contains_phrase(description, term)), None
        )
        if description_term:
            description_matches += 1
            score += 8
            matched_terms.append(
                label
                if normalize_search_text(label) == normalize_search_text(description_term)
                else f"{label} → {description_term}"
            )
            continue

        all_terms_matched = False

    normalized_query = normalize_search_text(query.keywords)
    if normalized_query and _contains_phrase(title, normalized_query):
        score += 30
    elif len(normalized_query.split()) > 1 and _contains_phrase(
        description, normalized_query
    ):
        score += 15

    if title_matches and description_matches:
        match_type = "title + description match"
    elif title_matches:
        match_type = "title match"
    elif description_matches:
        match_type = "description match"
    else:
        match_type = None

    return RelevanceMatch(
        score=min(score, 100),
        matched_terms=tuple(matched_terms),
        match_type=match_type,
        all_terms_matched=all_terms_matched,
    )


def title_has_query_signal(title: str, query: SearchQuery) -> bool:
    """Cheap prefilter for providers whose list endpoint omits descriptions."""
    if not query.keywords.strip():
        return True
    probe = JobPosting("", title, "", "", "", None, "")
    match = evaluate_relevance(probe, query)
    return bool(match.match_type and "title" in match.match_type)
