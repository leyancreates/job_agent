import json
from types import SimpleNamespace

import pytest

from google_docs_editor import Bullet, apply_tailoring, improve_bullets


class FakeResponses:
    def create(self, **kwargs):
        assert kwargs["text"]["format"]["strict"] is True
        return SimpleNamespace(output_text=json.dumps({"bullets": ["Built concise reports with Excel."]}))


def test_improve_bullets_uses_structured_output():
    client = SimpleNamespace(responses=FakeResponses())
    result = improve_bullets(
        "Excel reporting role",
        [Bullet("Made reports using Excel", 1, 25)],
        client=client,
    )
    assert result == ["Built concise reports with Excel."]


def test_improve_bullets_rejects_empty_job_description():
    with pytest.raises(ValueError):
        improve_bullets(" ", [Bullet("A bullet", 1, 9)], client=object())


def test_apply_tailoring_validates_counts():
    with pytest.raises(ValueError):
        apply_tailoring("doc", [Bullet("A bullet", 1, 9)], [])

