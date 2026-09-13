import course_manager
import academic_progress


def test_progress_engine_recognizes_practiced_status():
    assert "practiced" in academic_progress.STATUS_WEIGHTS
    assert academic_progress.STATUS_WEIGHTS["practiced"] == 35


def test_course_manager_currently_does_not_accept_practiced_status():
    assert "practiced" not in course_manager.VALID_TOPIC_STATUSES