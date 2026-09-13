import course_manager
import academic_progress


def test_progress_engine_recognizes_practiced_status():
    assert "practiced" in academic_progress.STATUS_WEIGHTS
    assert academic_progress.STATUS_WEIGHTS["practiced"] == 35


def test_course_manager_accepts_practiced_status():
    assert "practiced" in course_manager.VALID_TOPIC_STATUSES

    topic = course_manager._normalise_topic({
        "name": "LU Factorization",
        "status": "practiced",
    })

    assert topic["status"] == "practiced"


def test_practiced_is_lower_priority_than_not_started_but_above_mastered(monkeypatch):
    course = {
        "id": "ma103n",
        "code": "MA103N",
        "name": "Linear Algebra",
        "topics": [
            {"name": "Mastered", "status": "mastered"},
            {"name": "Practiced", "status": "practiced"},
            {"name": "Not Started", "status": "not_started"},
            {"name": "Review", "status": "review"},
            {"name": "Weak", "status": "weak"},
        ],
    }

    monkeypatch.setattr(
        course_manager,
        "find_course",
        lambda identifier: course,
    )

    rows = course_manager.recommend_next_topics(
        "ma103n",
        limit=10,
    )

    assert [
        item["status"]
        for item in rows
    ] == [
        "weak",
        "review",
        "not_started",
        "practiced",
    ]
