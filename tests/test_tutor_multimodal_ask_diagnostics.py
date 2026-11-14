"""Regression: selected PDF evidence errors must not claim an empty question.

Synthetic fixture only: no personal data, network, or paid provider call.
"""
from html import unescape
import re

import pytest

from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebValidationError
from personal_learning_assistant.ui.web.multimodal import evidence_validation_error
from tests.test_phase7_5_academic_agent_web import FakeWebService, fake_web_app


@pytest.mark.parametrize(
    "reason, expected",
    [
        (
            "Cloud answering is local-only until a cost bound and exact consent are configured",
            "per-request cost allowance is zero",
        ),
        ("Consent required or source/provider/scope changed", "permission is missing"),
        ("Monthly budget exceeded; local-only is the default", "monthly cloud-answering budget"),
        ("Selected source/version/location is unavailable; review it again", "reselect the page"),
        ("Question cannot be empty.", "Enter a question before sending"),
        ("Tutor session is not active.", "no longer active"),
    ],
)
def test_ask_failure_reports_actual_safe_reason_and_retains_draft(reason, expected):
    class RefusingService(FakeWebService):
        def __init__(self):
            super().__init__()
            self.session["metadata"] = {
                "mm_selection": {"kind": "pdf_page"},
                "mm_sources": [
                    {"name": "Synthetic eigenvalues.pdf", "location": "Page 2", "origin": "embedded_text"}
                ],
            }

        def ask(self, session_id, question, **kwargs):
            self.ask_calls += 1
            raise AcademicAgentWebValidationError(reason)

    service = RefusingService()
    app = fake_web_app(service)
    draft = "Explain the selected evidence and point out anything uncertain."
    response = app.test_client().post(
        "/agent/sessions/session-1/ask",
        data={
            "csrf_token": app.extensions["tutor_action_csrf"],
            "question": draft,
            "request_id": "same-request-on-retry",
        },
    )
    assert response.status_code == 400
    assert expected in response.text
    assert "Question cannot be empty or the tutor session is not active." not in response.text
    value = re.search(r'<textarea[^>]*id="agent-question"[^>]*>(.*?)</textarea>',
                      response.text, re.S)
    assert value is not None and unescape(value.group(1)) == draft
    assert 'value="same-request-on-retry"' in response.text
    assert service.ask_calls == 1
    assert service.llm_calls == 0
    assert service.session_view("session-1")["turns"] == []


def test_unknown_validation_detail_never_leaks_into_tutor_page():
    class RefusingService(FakeWebService):
        def ask(self, session_id, question, **kwargs):
            raise AcademicAgentWebValidationError(
                "PRIVATE_TOKEN_AND_LOCAL_DATABASE_PATH_MUST_NOT_LEAK"
            )

    app = fake_web_app(RefusingService())
    response = app.test_client().post(
        "/agent/sessions/session-1/ask",
        data={"csrf_token": app.extensions["tutor_action_csrf"], "question": "Why?"},
    )
    assert response.status_code == 400
    assert "PRIVATE_TOKEN_AND_LOCAL_DATABASE_PATH_MUST_NOT_LEAK" not in response.text
    assert "current source or permissions" in response.text


@pytest.mark.parametrize("detail, expected", [
    (
        "Set a conservative provider cost bound before cloud answering",
        "explicit per-request cost bound",
    ),
    (
        "Configure a trusted HTTPS provider and model locally",
        "trusted HTTPS provider",
    ),
    (
        "PRIVATE_DATABASE_PATH_AND_PROVIDER_TOKEN",
        "Evidence action could not be completed",
    ),
])
def test_multimodal_review_errors_are_safe_json(detail, expected):
    app = fake_web_app(FakeWebService())
    with app.app_context():
        response, code = evidence_validation_error(ValueError(detail))
        assert code == 400
        assert response.is_json
        message = response.get_json()["error"]
        assert expected in message
        assert "PRIVATE_DATABASE_PATH_AND_PROVIDER_TOKEN" not in message


@pytest.mark.parametrize("error_type, sqlite_code, expected", [
    ("operational", "SQLITE_BUSY", "busy or locked"),
    ("operational", "SQLITE_READONLY", "read-only"),
    ("operational", "SQLITE_FULL", "insufficient space"),
    ("operational", "SQLITE_IOERR", "I/O or integrity"),
    ("integrity", "SQLITE_CONSTRAINT_FOREIGNKEY", "missing academic record"),
    ("operational", "SQLITE_ERROR", "schema could not complete"),
])
def test_sqlite_save_failures_are_classified_without_private_details(
    error_type, sqlite_code, expected,
):
    import sqlite3
    from personal_learning_assistant.services.academic_agent_web_service import (
        _safe_tutor_persistence_error,
    )

    exception_class = (
        sqlite3.IntegrityError if error_type == "integrity"
        else sqlite3.OperationalError
    )
    error = exception_class("PRIVATE_STUDENT_SOURCE_AND_PATH")
    error.sqlite_errorname = sqlite_code
    message = _safe_tutor_persistence_error(error)
    assert expected in message
    assert "PRIVATE_STUDENT_SOURCE_AND_PATH" not in message


def test_tutor_repository_save_failure_message_is_whitelisted_and_draft_retained():
    from personal_learning_assistant.services.academic_agent_web_service import (
        AcademicAgentWebUnavailableError,
    )

    class LockedService(FakeWebService):
        def ask(self, session_id, question, **kwargs):
            raise AcademicAgentWebUnavailableError(
                "Academic database is busy or locked. Stop duplicate ANVAYA processes, "
                "then check local storage before retrying; the response was not confirmed saved."
            )

    app = fake_web_app(LockedService())
    draft = "Keep this unsent eigenvector question"
    response = app.test_client().post(
        "/agent/sessions/session-1/ask",
        data={"csrf_token": app.extensions["tutor_action_csrf"], "question": draft},
    )
    assert response.status_code == 503
    assert "Academic database is busy or locked." in response.text
    assert draft in response.text
