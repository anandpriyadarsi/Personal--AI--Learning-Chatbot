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
