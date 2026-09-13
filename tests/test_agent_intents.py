import personal_academic_agent


def test_project_course_score_routes_to_projection():
    """
    Regression test for the old V13 routing conflict.

    "project course score" used to match the generic "course score"
    grade route before the projection route.
    """
    intent = personal_academic_agent.classify_intent(
        "Project course score"
    )

    assert intent == "COURSE_PROJECTION"


def test_project_my_final_course_score_routes_to_projection():
    """
    Regression test for the help-menu example.

    The agent help text suggests "Project my final course score",
    so that phrase must reach the projection tool.
    """
    intent = personal_academic_agent.classify_intent(
        "Project my final course score"
    )

    assert intent == "COURSE_PROJECTION"


def test_explicit_project_final_score_routes_to_projection():
    intent = personal_academic_agent.classify_intent(
        "Project final score"
    )

    assert intent == "COURSE_PROJECTION"


def test_plain_course_score_still_routes_to_course_grade():
    """
    Regression protection: a non-projection request for current course
    score should still open course-grade intelligence.
    """
    intent = personal_academic_agent.classify_intent(
        "Show course score"
    )

    assert intent == "COURSE_GRADE"


def test_plain_course_grade_still_routes_to_course_grade():
    intent = personal_academic_agent.classify_intent(
        "Show course grade"
    )

    assert intent == "COURSE_GRADE"
