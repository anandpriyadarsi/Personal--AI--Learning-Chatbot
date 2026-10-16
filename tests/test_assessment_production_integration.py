"""Production-scoped extended assessment, always against disposable SQLite.

Live academic rows are NEVER used. Opt-in migration and route registration
must not change normal exam/assessment semantics or trusted mastery signals.
"""
import json
import sqlite3

import pytest

from test_assessment_studio_phase_c import Clock, _database, _service
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
from personal_learning_assistant.services.assessment_execution_service import AssessmentExecutionService
from personal_learning_assistant.ui.web import create_app


def _production(tmp_path, *, paper=False):
    if paper:
        from test_assessment_studio_phase_b import _database as import_db, _raw, _subjective_package
        from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
        path = import_db(tmp_path)
        test = _subjective_package()
        test["assessment"]["mode"] = "practice"
        pack = AssessmentPackageService(path)
        batch = pack.stage_upload("reviewed-paper.json", _raw(test))
        assessment = pack.approve(batch["id"])
    else:
        path = _database(tmp_path)
        assessment = "assessment-1"
        with sqlite3.connect(path) as db:
            db.execute("UPDATE assessment_runtime_specs SET mode='practice'")
    assert apply_migrations(path, enable_extended_assessment=True) == (15,)
    clock = Clock()
    def extended():
        return AssessmentExecutionService(path, now_fn=clock, production=True)
    app = create_app({
        "TESTING": True,
        "ASSESSMENT_EXTENDED_ENABLED": True,
        "ASSESSMENT_RUNNER_SERVICE_FACTORY": lambda: AssessmentRunnerService(path, now_fn=clock),
        "ASSESSMENT_EXTENDED_SERVICE_FACTORY": extended,
    })
    return app, path, assessment, extended, clock


def test_0015_requires_explicit_opt_in_and_preserves_normal_initial_boot(tmp_path):
    path = _database(tmp_path)
    assert apply_migrations(path) == ()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 14
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='assessment_extended_scope'").fetchone()[0] == 0
    assert apply_migrations(path, enable_extended_assessment=True) == (15,)
    assert apply_migrations(path) == ()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone()[0] == 15
        assert db.execute("SELECT scope FROM assessment_extended_scope").fetchone()[0] == "local-self-study-v1"
        assert db.execute("SELECT count(*) FROM assessment_test_sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM question_attempts").fetchone()[0] == 0
    # The synthetic candidate tables must not be created or trusted.
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='assessment_candidate_execution'").fetchone()[0] == 0


def test_normal_assessment_preflight_opt_in_resume_and_reject_legacy_mutation(tmp_path):
    app, path, aid, extended, clock = _production(tmp_path)
    client = app.test_client()
    original = client.get("/assessments/tests/" + aid)
    assert original.status_code == 200
    assert "Start with Pause/Resume" in original.get_data(as_text=True)
    started = client.post("/assessments/tests/" + aid + "/start",
                          data={"confirmed": "1", "extended_kind": "online_timed"})
    assert started.status_code == 303
    assert "/assessments/sessions/" in started.location
    redirected = client.get(started.location)
    assert redirected.status_code == 303
    assert "/assessments/extended/sessions/" in redirected.location
    page = client.get(redirected.location)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Private self-study" in html
    assert "SECRET-SUBJECTIVE-SOLUTION" not in html
    sid = started.location.rsplit("/", 1)[1]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM assessment_extended_execution WHERE session_id=?", (sid,)).fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='assessment_candidate_execution'").fetchone()[0] == 0
    clock.advance(10)
    q = extended().state(sid)["questions"][0]
    def command(name, **data):
        import uuid
        return extended().command(sid, name, {
            "request_id": str(uuid.uuid4()), "expected_revision": extended().state(sid)["revision"], **data
        })
    command("pause", question_id=q["session_question_id"],
            expected_response_revision=q["response_revision"],
            response={"selected_option_ids": ["B"]}, marked=False)
    frozen = extended().state(sid)["remaining_ms"]
    clock.advance(1800)
    assert extended().state(sid)["remaining_ms"] == frozen
    resumed = client.get("/assessments/tests/" + aid)
    assert resumed.status_code == 200
    assert "Resume active test" in resumed.get_data(as_text=True)
    command("resume")
    assert extended().state(sid)["questions"][0]["response"]["selected_option_ids"] == ["B"]
    # Legacy runner must reject accidental auto-submit/expiry for this session.
    with pytest.raises(Exception, match="extended attempt|candidate workspace"):
        _service(path, clock).submit(sid)


def test_paper_uses_approved_import_only_and_never_creates_official_grade(tmp_path):
    app, path, aid, extended, _ = _production(tmp_path, paper=True)
    client = app.test_client()
    before = client.get("/assessments/tests/" + aid)
    assert before.status_code == 200
    assert "Start handwritten paper practice" in before.get_data(as_text=True)
    bad = client.post("/assessments/tests/" + aid + "/start",
                      data={"confirmed": "1", "extended_kind": "paper_subjective"})
    assert bad.status_code in (400, 422)
    started = client.post("/assessments/tests/" + aid + "/start",
                          data={"confirmed": "1", "extended_kind": "paper_subjective",
                                "self_review_acknowledged": "1"})
    assert started.status_code == 303
    sid = started.location.rsplit("/", 1)[1]
    view = extended().state(sid)
    assert view["kind"] == "paper_subjective"
    assert view["package_identity"]["production_authority"] == "BLOCKED"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM question_attempts").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM assessment_response_evaluations").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM topic_progress_events").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM assessment_extended_self_reviews").fetchone()[0] == 0


def test_feature_off_default_and_missing_migration_fail_closed(tmp_path):
    path = _database(tmp_path)
    clock = Clock()
    app = create_app({
        "TESTING": True,
        "ASSESSMENT_RUNNER_SERVICE_FACTORY": lambda: AssessmentRunnerService(path, now_fn=clock),
        "ASSESSMENT_EXTENDED_ENABLED": False,
    })
    client = app.test_client()
    assert "Start with Pause/Resume" not in client.get("/assessments/tests/assessment-1").get_data(as_text=True)
    assert client.get("/assessments/extended/sessions/not-real").status_code == 404
    with pytest.raises(sqlite3.Error):
        AssessmentExecutionService(path, now_fn=clock, production=True).state("x")
