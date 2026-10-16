import re
import sqlite3
import pytest
from test_assessment_pause_paper import candidate, command


def app_for(s):
    from personal_learning_assistant.ui.web.assessment_execution_candidate import (
        create_candidate_app,
    )

    return create_candidate_app(
        s, secret_key=b"fixture-secret-only-do-not-use-in-production"
    )


def form(client, s, sid):
    html = client.get(f"/assessments/candidate/sessions/{sid}").text
    return {
        "mutation_token": re.search(r'name="mutation_token" value="([^"]+)"', html)[1],
        "request_id": "request-web-001",
        "expected_revision": s.state(sid)["revision"],
    }


def test_new_routes_are_not_mounted_in_normal_app():
    from personal_learning_assistant.ui.web import create_app

    app = create_app({"TESTING": True})
    # Learning Studio legitimately has a /learning/.../coverage/candidate
    # route. Only the standalone Assessment fixture URL must be absent here.
    assert not any(
        str(rule).startswith("/assessments/candidate/")
        for rule in app.url_map.iter_rules()
    )


def test_same_origin_token_and_private_projection(tmp_path):
    s, sid, path, clock = candidate(tmp_path, paper=True)
    app = app_for(s)
    client = app.test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    html = client.get(url).text
    assert (
        "Reviewed worked solution" not in html and "Reviewed method marks" not in html
    )
    assert "Reviewed worked solution" not in client.get(url + "/state").text
    payload = form(client, s, sid)
    for headers, data in (
        ({}, payload),
        ({"Origin": "http://evil.invalid"}, payload),
        ({"Origin": "http://localhost"}, {**payload, "mutation_token": "forged"}),
        ({"Origin": "http://localhost", "Sec-Fetch-Site": "cross-site"}, payload),
    ):
        assert (
            client.post(url + "/pause", json=data, headers=headers).status_code == 403
        )
    ok = client.post(
        url + "/pause", json=payload, headers={"Origin": "http://localhost"}
    )
    assert ok.status_code == 200 and ok.json["state"]["status"] == "paused"
    assert ok.headers["Cache-Control"] == "no-store"
    assert (
        "traceback"
        not in client.post(
            url + "/resume", json={}, headers={"Origin": "http://localhost"}
        ).text.lower()
    )


def test_native_forms_work_and_get_does_not_write(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    with sqlite3.connect(path) as db:
        before = list(db.iterdump())
    payload = form(client, s, sid)
    with sqlite3.connect(path) as db:
        assert list(db.iterdump()) == before
    result = client.post(
        url + "/pause", data=payload, headers={"Origin": "http://localhost"}
    )
    assert result.status_code == 303
    assert "Paused — answers saved" in client.get(url).text


def test_native_paper_guides_and_missing_marks(tmp_path):
    s, sid, _, _ = candidate(tmp_path, paper=True)
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    command(s, sid, "finish_solving")
    q = s.state(sid)["questions"][0]
    payload = {**form(client, s, sid), "question_id": q["session_question_id"]}
    assert (
        client.post(
            url + "/reveal", data=payload, headers={"Origin": "http://localhost"}
        ).status_code
        == 303
    )
    html = client.get(url).text
    assert (
        "Reviewed worked solution" in html
        and "No verified step allocation available" in html
    )
    assert "Self-assessed, not independently graded" in html
    assert client.get(url + "/review-summary").json["missing"] == 4


@pytest.mark.parametrize(
    "response",
    [
        {"selected_option_ids": True},
        {"selected_option_ids": ["B"], "solution": "forged"},
        {"selected_option_ids": [{}]},
        {"selected_option_ids": ["not-an-option"]},
        {"selected_option_ids": ["B"], "mode": "practice"},
    ],
)
def test_invalid_response_is_safe_validation_error(tmp_path, response):
    s, sid, path, clock = candidate(tmp_path)
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    q = s.state(sid)["questions"][0]
    payload = {
        **form(client, s, sid),
        "question_id": q["session_question_id"],
        "expected_response_revision": 1,
        "response": response,
    }
    result = client.post(
        url + "/save", json=payload, headers={"Origin": "http://localhost"}
    )
    assert result.status_code == 422 and result.json["ok"] is False
    assert s.state(sid)["questions"][0]["response"] == {}


def test_native_stale_pause_preserves_visible_unsaved_choice(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    q = s.state(sid)["questions"][0]
    payload = form(client, s, sid)
    command(s, sid, "pause")
    result = client.post(
        url + "/pause",
        data={
            **payload,
            "question_id": q["session_question_id"],
            "expected_response_revision": "1",
            "option_ids": "A",
        },
        headers={"Origin": "http://localhost"},
    )
    assert result.status_code == 409
    assert re.search(r'<input[^>]*value="A"[^>]*checked', result.text)
    assert "Unsaved input retained" in result.text
    assert s.state(sid)["questions"][0]["response"] == {}


def test_reopened_expired_online_attempt_can_confirm_timeout(tmp_path):
    s, sid, path, clock = candidate(tmp_path)
    clock.advance(61)
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    html = client.get(url).text
    assert "Confirm timeout" in html
    result = client.post(
        url + "/submit",
        data=form(client, s, sid),
        headers={"Origin": "http://localhost"},
    )
    assert result.status_code == 303
    with sqlite3.connect(path) as db:
        assert (
            db.execute(
                "SELECT status FROM assessment_test_sessions WHERE id=?", (sid,)
            ).fetchone()[0]
            == "expired"
        )
    assert "Confirm timeout" not in client.get(url).text


def test_native_timer_uses_ceiling_milliseconds(tmp_path):
    from datetime import timedelta

    s, sid, path, clock = candidate(tmp_path)
    clock.value += timedelta(milliseconds=59999)
    client = app_for(s).test_client()
    html = client.get(f"/assessments/candidate/sessions/{sid}").text
    assert '<strong id="timer">00:01</strong>' in html


def test_native_criterion_reasons_do_not_become_step_awards(tmp_path):
    from scripts.assessment_execution_fixture import create_fixture

    s, ids, key = create_fixture(tmp_path / "fixture")
    sid = ids["paper"]
    command(s, sid, "finish_solving")
    q = s.state(sid)["questions"][0]
    command(s, sid, "reveal", question_id=q["session_question_id"])
    client = app_for(s).test_client()
    url = f"/assessments/candidate/sessions/{sid}"
    response = client.post(
        url + "/self_save",
        data={
            **form(client, s, sid),
            "question_id": q["session_question_id"],
            "step_factor": "1",
            "step_forward": "1",
            "step_back": "1",
            "criterion_reason_forward": "Checked substitution",
        },
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 303
    item = s.state(sid)["review"]["items"][q["session_question_id"]]
    assert item["awarded_marks_milli"] == 3000 and item["step_reasons"] == {
        "forward": "Checked substitution"
    }


def test_synthetic_preview_root_is_discoverable_and_does_not_write(tmp_path):
    """The fixture server / route is a chooser, not a missing-page 404.

    Only the two disposable session IDs are linked. Reading the chooser must
    not alter either academic fixtures or submission/grade state.
    """
    from scripts.assessment_execution_fixture import create_fixture
    from personal_learning_assistant.ui.web.assessment_execution_candidate import create_candidate_app

    service, ids, key = create_fixture(tmp_path / "fixture")
    with sqlite3.connect(service.repository.path) as db:
        before = list(db.iterdump())

    app = create_candidate_app(service, secret_key=key, landing_sessions=ids)
    client = app.test_client()
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers["Cache-Control"] == "no-store"
    assert "Choose how you want to practise" in home.get_data(as_text=True)
    assert "Synthetic learning demo" in home.get_data(as_text=True)
    for kind in ("online", "paper"):
        address = "/assessments/candidate/sessions/" + ids[kind]
        assert address in home.get_data(as_text=True)
        assert client.get(address).status_code == 200
    assert "/assessments/extended/sessions/" not in home.get_data(as_text=True)

    with sqlite3.connect(service.repository.path) as db:
        assert list(db.iterdump()) == before


def test_main_assessment_page_displays_preview_with_feature_disabled():
    """Display the demo invitation without opening installed extended storage."""
    from personal_learning_assistant.ui.web import create_app
    app = create_app({"TESTING": True, "ASSESSMENT_EXTENDED_ENABLED": False})
    client = app.test_client()
    page = client.get("/assessments")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Pause practice" in body
    assert "handwritten self-check" in body
    assert "http://127.0.0.1:8766/" in body
    assert "python scripts/assessment_execution_fixture.py --port 8766" in body
    assert "Your normal assessments are unchanged" in body
    assert client.get("/assessments/extended/sessions/does-not-exist").status_code == 404
