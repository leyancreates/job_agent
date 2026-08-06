"""Resume-to-job matching backed by the OpenAI Responses API."""

from .models import CompatibilityAssessment, JobMatch, MatchResult
from .service import (
    MatchAnalysisError,
    MatchSelectionError,
    ResumeRequiredError,
    analyze_job_matches,
)

__all__ = [
    "CompatibilityAssessment",
    "JobMatch",
    "MatchAnalysisError",
    "MatchResult",
    "MatchSelectionError",
    "ResumeRequiredError",
    "analyze_job_matches",
]
