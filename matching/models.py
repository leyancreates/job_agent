"""Validated models for resume-to-job match guidance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobs.models import JobPosting

RECOMMENDATIONS = {"Strong match", "Possible match", "Low match"}
COMPATIBILITY_STATUSES = {"Compatible", "Potential concern", "Unclear"}
MATCH_FIELDS = {
    "job_id",
    "overall_score",
    "skills_score",
    "experience_score",
    "education_domain_score",
    "location_work_authorization",
    "matched_strengths",
    "missing_or_weak_qualifications",
    "factual_concerns",
    "recommendation",
    "explanation",
}


def recommendation_for_score(score: int) -> str:
    if score >= 75:
        return "Strong match"
    if score >= 45:
        return "Possible match"
    return "Low match"


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


def _score(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError(f"{field} must be an integer from 0 to 100.")
    return value


def _string_list(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list.")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must contain only non-empty strings.")
        result.append(item.strip())
    return tuple(result)


@dataclass(frozen=True)
class CompatibilityAssessment:
    status: str
    explanation: str

    @classmethod
    def from_payload(cls, payload: Any) -> CompatibilityAssessment | None:
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ValueError("location_work_authorization must be an object or null.")
        if set(payload) != {"status", "explanation"}:
            raise ValueError("location_work_authorization contains unexpected fields.")
        status = _required_string(payload, "status")
        if status not in COMPATIBILITY_STATUSES:
            raise ValueError("Unsupported location/work-authorization status.")
        return cls(status=status, explanation=_required_string(payload, "explanation"))


@dataclass(frozen=True)
class MatchResult:
    job_id: str
    overall_score: int
    skills_score: int
    experience_score: int
    education_domain_score: int
    location_work_authorization: CompatibilityAssessment | None
    matched_strengths: tuple[str, ...]
    missing_or_weak_qualifications: tuple[str, ...]
    factual_concerns: tuple[str, ...]
    recommendation: str
    explanation: str

    @classmethod
    def from_payload(cls, payload: Any) -> MatchResult:
        if not isinstance(payload, dict):
            raise ValueError("Each match result must be an object.")
        if set(payload) != MATCH_FIELDS:
            raise ValueError("Match result fields do not match the expected schema.")
        overall_score = _score(payload, "overall_score")
        supplied_recommendation = _required_string(payload, "recommendation")
        if supplied_recommendation not in RECOMMENDATIONS:
            raise ValueError("Unsupported match recommendation.")
        recommendation = recommendation_for_score(overall_score)
        if supplied_recommendation != recommendation:
            raise ValueError("Recommendation does not match the overall score.")
        return cls(
            job_id=_required_string(payload, "job_id"),
            overall_score=overall_score,
            skills_score=_score(payload, "skills_score"),
            experience_score=_score(payload, "experience_score"),
            education_domain_score=_score(payload, "education_domain_score"),
            location_work_authorization=CompatibilityAssessment.from_payload(
                payload.get("location_work_authorization")
            ),
            matched_strengths=_string_list(payload, "matched_strengths"),
            missing_or_weak_qualifications=_string_list(
                payload, "missing_or_weak_qualifications"
            ),
            factual_concerns=_string_list(payload, "factual_concerns"),
            recommendation=recommendation,
            explanation=_required_string(payload, "explanation"),
        )


@dataclass(frozen=True)
class JobMatch:
    job: JobPosting
    result: MatchResult
