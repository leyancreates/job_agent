import json
from types import SimpleNamespace

import pytest

from jobs.models import JobPosting
from matching.cache import MatchCache
from matching.models import recommendation_for_score
from matching.service import (
    MatchAnalysisError,
    MatchSelectionError,
    ResumeRequiredError,
    analyze_job_matches,
    match_cache_key,
)


def job(
    identifier: str,
    *,
    title: str = "Data Analyst",
    description: str = "Analyze data using Python and SQL.",
) -> JobPosting:
    return JobPosting(
        company=f"Company {identifier}",
        title=title,
        location="Toronto, Canada",
        job_url=f"https://example.com/jobs/{identifier}",
        source="Greenhouse",
        posted_date="2026-08-01T00:00:00Z",
        job_description=description,
    )


def match_payload(job_id: str, score: int = 80, *, compatibility=None) -> dict:
    return {
        "job_id": job_id,
        "overall_score": score,
        "skills_score": score,
        "experience_score": score,
        "education_domain_score": score,
        "location_work_authorization": compatibility,
        "matched_strengths": ["Resume explicitly lists Python."],
        "missing_or_weak_qualifications": ["Unknown: work authorization is not stated."],
        "factual_concerns": [],
        "recommendation": recommendation_for_score(score),
        "explanation": "The explicit skills align, while some requirements are unknown.",
    }


class FakeResponses:
    def __init__(self, builder):
        self.builder = builder
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        request = json.loads(kwargs["input"])
        return SimpleNamespace(output_text=json.dumps(self.builder(request)))


def fake_client(builder):
    responses = FakeResponses(builder)
    return SimpleNamespace(responses=responses), responses


def valid_builder(request):
    return {
        "matches": [
            match_payload(item["job_id"], score=82 - index * 20)
            for index, item in enumerate(request["jobs"])
        ]
    }


def test_multi_job_batch_uses_strict_responses_schema_and_minimal_input():
    client, responses = fake_client(valid_builder)
    results = analyze_job_matches(
        "Python, SQL, and analytics experience.",
        [job("one"), job("two", title="Business Analyst")],
        client=client,
        model="test-model",
        cache=MatchCache(),
    )

    assert len(responses.calls) == 1
    assert [result.result.overall_score for result in results] == [82, 62]
    call = responses.calls[0]
    assert call["store"] is False
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["text"]["format"]["schema"]["properties"]["matches"]["minItems"] == 2
    sent_jobs = json.loads(call["input"])["jobs"]
    assert len(sent_jobs) == 2
    assert all("job_url" not in sent_job for sent_job in sent_jobs)


def test_cache_prevents_duplicate_requests_and_varies_with_resume():
    client, responses = fake_client(valid_builder)
    cache = MatchCache()
    selected_job = job("cached")

    first = analyze_job_matches(
        "Python resume", [selected_job], client=client, model="test-model", cache=cache
    )
    second = analyze_job_matches(
        "Python resume", [selected_job], client=client, model="test-model", cache=cache
    )
    analyze_job_matches(
        "Different resume", [selected_job], client=client, model="test-model", cache=cache
    )

    assert first == second
    assert len(responses.calls) == 2


def test_partial_cache_hit_batches_only_uncached_jobs():
    client, responses = fake_client(valid_builder)
    cache = MatchCache()
    first_job = job("first")
    second_job = job("second")

    analyze_job_matches("Resume", [first_job], client=client, cache=cache)
    combined = analyze_job_matches(
        "Resume", [first_job, second_job], client=client, cache=cache
    )

    assert len(responses.calls) == 2
    assert len(json.loads(responses.calls[1]["input"])["jobs"]) == 1
    assert {item.job for item in combined} == {first_job, second_job}


def test_cache_key_uses_resume_description_and_model():
    original = job("key")
    changed_description = job("key", description="A different job description.")
    base = match_cache_key("Resume", original, "model-a")

    assert base != match_cache_key("Changed resume", original, "model-a")
    assert base != match_cache_key("Resume", changed_description, "model-a")
    assert base != match_cache_key("Resume", original, "model-b")


@pytest.mark.parametrize("score", [0, 100])
def test_score_boundaries_are_accepted(score):
    client, _ = fake_client(
        lambda request: {"matches": [match_payload(request["jobs"][0]["job_id"], score)]}
    )
    result = analyze_job_matches(
        "Resume", [job(f"score-{score}")], client=client, cache=MatchCache()
    )
    assert result[0].result.overall_score == score


@pytest.mark.parametrize("score", [-1, 101])
def test_out_of_range_scores_are_rejected(score):
    client, _ = fake_client(
        lambda request: {"matches": [match_payload(request["jobs"][0]["job_id"], score)]}
    )
    with pytest.raises(MatchAnalysisError, match="unusable match analysis"):
        analyze_job_matches("Resume", [job("invalid")], client=client, cache=MatchCache())


def test_missing_information_remains_unknown_and_compatibility_is_omitted():
    client, _ = fake_client(valid_builder)
    result = analyze_job_matches(
        "Python experience only", [job("unknown")], client=client, cache=MatchCache()
    )[0].result

    assert result.location_work_authorization is None
    assert result.missing_or_weak_qualifications == (
        "Unknown: work authorization is not stated.",
    )


def test_malformed_model_output_is_rejected():
    responses = FakeResponses(lambda _request: {})
    client = SimpleNamespace(responses=responses)
    with pytest.raises(MatchAnalysisError, match="unusable match analysis"):
        analyze_job_matches("Resume", [job("malformed")], client=client, cache=MatchCache())


def test_schema_validation_rejects_missing_fields():
    def incomplete(request):
        return {"matches": [{"job_id": request["jobs"][0]["job_id"], "overall_score": 50}]}

    client, _ = fake_client(incomplete)
    with pytest.raises(MatchAnalysisError, match="unusable match analysis"):
        analyze_job_matches("Resume", [job("incomplete")], client=client, cache=MatchCache())


def test_schema_validation_rejects_extra_fields_and_inconsistent_recommendation():
    def invalid(request):
        item = match_payload(request["jobs"][0]["job_id"], 80)
        item["recommendation"] = "Low match"
        item["unexpected"] = True
        return {"matches": [item]}

    client, _ = fake_client(invalid)
    with pytest.raises(MatchAnalysisError, match="unusable match analysis"):
        analyze_job_matches("Resume", [job("extra")], client=client, cache=MatchCache())


def test_resume_and_batch_validation_happen_before_api_calls():
    client, responses = fake_client(valid_builder)
    with pytest.raises(ResumeRequiredError, match="Load your resume"):
        analyze_job_matches(" ", [job("one")], client=client, cache=MatchCache())
    with pytest.raises(MatchSelectionError, match="no more than 10"):
        analyze_job_matches(
            "Resume",
            [job(str(index)) for index in range(11)],
            client=client,
            cache=MatchCache(),
        )
    assert not responses.calls
