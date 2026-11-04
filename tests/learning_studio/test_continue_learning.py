"""Persistent, revision-scoped Continue Learning uses existing reading events only."""
from copy import deepcopy

from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app

from .helpers import catalogue, package
from .test_service import studio, publish


def _two_lessons():
    p = package(mapped=True)
    extra = deepcopy(p["sections"][0])
    extra["id"] = "lesson-2"
    extra["title"] = "Next lesson after reading"
    extra["pages"] = [2]
    for block in extra["blocks"]:
        block["pages"] = [2]
    p["sections"].append(extra)
    return p


def _event(event_id, section_id, *, completed=None):
    event = {"event_id": event_id, "section_id": section_id, "view": "learn"}
    if completed is not None:
        event["completed"] = completed
    return event


def test_empty_resume_does_not_create_storage(studio):
    assert studio.resume_learning() is None
    assert not studio.store.path.exists()


def test_reading_position_completion_and_restart_resume(studio):
    p = publish(studio, _two_lessons())
    assert studio.resume_learning() is None

    studio.record_progress(p["module_id"], 1, _event("reading-lesson-one", "lesson-1"))
    resume = studio.resume_learning()
    assert resume["next_section"] == "lesson-1"
    assert resume["completed_count"] == 0
    assert resume["total_lessons"] == 2

    studio.record_progress(p["module_id"], 1, _event("complete-lesson-one", "lesson-1", completed=True))
    restarted = LearningStudioService(
        studio.store.path, source_loader=studio.source_loader, catalogue_loader=catalogue
    )
    resume = restarted.resume_learning("c0")
    assert resume["next_section"] == "lesson-2"
    assert resume["next_title"] == "Next lesson after reading"
    assert resume["completed_count"] == 1
    assert resume["all_completed"] is False
    assert restarted.resume_learning("c1") is None

    restarted.record_progress(p["module_id"], 1, _event("complete-lesson-two", "lesson-2", completed=True))
    done = restarted.resume_learning()
    assert done["all_completed"] is True
    assert done["next_section"] is None
    assert done["completed_count"] == 2


def test_active_revision_does_not_inherit_previous_revision_position(studio):
    p = publish(studio, _two_lessons())
    studio.record_progress(p["module_id"], 1, _event("complete-first-revision", "lesson-1", completed=True))
    next_revision = deepcopy(p)
    next_revision["module_revision"] = 2
    publish(studio, next_revision)
    assert studio.resume_learning() is None
    studio.record_progress(p["module_id"], 2, _event("reading-revision-two", "lesson-2"))
    assert studio.resume_learning()["next_section"] == "lesson-2"


def test_saved_resume_link_renders_on_learning_and_subject_page(studio):
    p = publish(studio, _two_lessons())
    studio.record_progress(p["module_id"], 1, _event("completed-first-screen", "lesson-1", completed=True))
    app = create_app({"TESTING": True, "LEARNING_STUDIO_SERVICE_FACTORY": lambda: studio})
    client = app.test_client()
    for path in ("/learning", "/learning/courses/c0"):
        response = client.get(path)
        assert response.status_code == 200
        text = response.get_data(as_text=True)
        assert "Continue Learning" in text
        assert "lesson-2" in text
        assert "1 of 2 lessons marked completed" in text
        assert "not assessment mastery" in text


def test_formal_assessment_link_uses_reviewed_course_not_quick_question(studio):
    publish(studio, _two_lessons())
    app = create_app({"TESTING": True, "LEARNING_STUDIO_SERVICE_FACTORY": lambda: studio})
    page = app.test_client().get("/learning/modules/synthetic/1?view=learn")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Practise this lesson" in html
    assert "Take a formal subject assessment in Assessment Studio" in html
    assert "/assessments/tests?course_id=c0" in html


def test_inline_lesson_mcq_keeps_grading_on_server(studio):
    p = publish(studio, _two_lessons())
    app = create_app({"TESTING": True, "LEARNING_STUDIO_SERVICE_FACTORY": lambda: studio})
    client = app.test_client()
    page = client.get("/learning/modules/synthetic/1?view=learn&section=lesson-1")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Check your understanding here" in html
    assert 'id="inline-question-q1"' in html
    assert 'data-question-id="q1"' in html
    assert 'name="mode" value="lesson"' in html
    assert "This is separate from formal Assessment Studio tests." in html
    # Correct answers and explanations are never included in the first-read markup.
    assert "Compare the original source." not in html
    token = app.extensions["learning_studio_csrf"]
    result = client.post(
        "/learning/modules/synthetic/1/attempts",
        data={
            "csrf_token": token, "event_id": "inline-fallback-1",
            "module_revision": "1", "source_sha256": p["source"]["sha256"],
            "question_id": "q1", "question_revision": "1",
            "selection": "0", "section": "lesson-1", "mode": "lesson",
        },
        follow_redirects=False,
    )
    assert result.status_code == 303
    assert "view=practice" in result.headers["Location"]
    assert studio.practice_state("synthetic", 1)["q1"]["attempt_count"] == 1
