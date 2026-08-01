import json

import pytest

import google_docs_reader
from google_docs_reader import ConfigurationError


def test_invalid_service_account_json_has_safe_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "not-json")
    with pytest.raises(ConfigurationError, match="not valid"):
        google_docs_reader._service_account_credentials()


def test_missing_google_configuration_has_safe_error(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET_FILE", raising=False)
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "missing-token.json"))
    with pytest.raises(ConfigurationError, match="not configured"):
        google_docs_reader._desktop_credentials()

