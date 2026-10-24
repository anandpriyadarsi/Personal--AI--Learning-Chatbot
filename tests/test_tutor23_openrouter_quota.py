"""Offline, no-credential regression tests for Tutor OpenRouter quota policy."""
from pathlib import Path
from unittest.mock import Mock

from scripts.tutor23_openrouter_preflight import (
    REQUIRED_QUOTA, quota_snapshot, upstream_rate_limit, save_report
)


def test_quota_reads_without_inference(monkeypatch):
    called = []
    def fake_get(url, **kwargs):
        called.append(url)
        response = Mock(status_code=200)
        response.json.return_value = {"data": {
            "free_model_daily_requests": {"used": 25, "limit": 50, "remaining": 25}
        }}
        return response
    monkeypatch.setattr("requests.get", fake_get)
    quota, error = quota_snapshot("never_logged")
    assert quota == {"used": 25, "limit": 50, "remaining": 25}
    assert error is None and called == ["https://openrouter.ai/api/v1/key"]
    assert REQUIRED_QUOTA == 25


def test_account_rate_limit_does_not_allow_fallback():
    response = Mock(status_code=429)
    response.json.return_value = {"error": {
        "code": 429, "metadata": {"error_type": "rate_limit_exceeded"}
    }}
    assert not upstream_rate_limit(response)


def test_provider_scoped_429_can_try_another_free_model():
    response = Mock(status_code=429)
    response.json.return_value = {"error": {
        "code": 429, "metadata": {"provider_code": 429}
    }}
    assert upstream_rate_limit(response)


def test_quota_read_failure_is_fail_closed(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"data": {"free_model_daily_requests": {}}}
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: response)
    quota, error = quota_snapshot("secret")
    assert quota is None and error is not None


def test_blocked_report_contains_no_key(tmp_path):
    save_report(tmp_path, [], {"used": 50, "limit": 50, "remaining": 0},
                blocked="insufficient_daily_quota")
    value = (tmp_path / "openrouter-preflight.json").read_text()
    assert "insufficient_daily_quota" in value
    assert "LLM_API_KEY" not in value
