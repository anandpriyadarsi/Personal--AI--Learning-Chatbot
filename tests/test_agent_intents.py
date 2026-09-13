import personal_academic_agent


def test_project_course_score_currently_routes_to_course_grade():
    """
    Characterization of the current V13 routing conflict.

    "project course score" is intended to mean a final-score projection,
    but the current substring order matches "course score" first and
    returns COURSE_GRADE.
    """
    intent = personal_academic_agent.classify_intent(
        "Project course score"
    )

    assert intent == "COURSE_GRADE"


def test_explicit_project_final_score_reaches_projection_handler():
    """
    Characterization of a phrase that currently reaches the intended
    projection route.
    """
    intent = personal_academic_agent.classify_intent(
        "Project final score"
    )

    assert intent == "COURSE_PROJECTION"
