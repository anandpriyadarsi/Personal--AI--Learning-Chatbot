from datetime import date, timedelta

import academic_calendar_planner


def _assessment(title, due_date):
    return {
        "id": title.lower().replace(" ", "-"),
        "course_id": "ma103n",
        "type": "quiz",
        "title": title,
        "due_date": due_date.isoformat(),
        "status": "pending",
    }


def test_overdue_block_logic_exists_when_called_directly(monkeypatch):
    """
    Characterization: the study-block engine already knows how to
    handle an overdue assessment if that assessment reaches it.
    """
    today = date(2026, 9, 13)
    overdue = _assessment(
        "Overdue Quiz",
        today - timedelta(days=2),
    )

    monkeypatch.setattr(
        academic_calendar_planner,
        "_today",
        lambda: today,
    )
    monkeypatch.setattr(
        academic_calendar_planner,
        "days_until",
        lambda due_date: -2,
    )

    blocks = (
        academic_calendar_planner
        .recommended_blocks_for_assessment(overdue)
    )

    assert blocks == [
        (
            today,
            90,
            "Immediate overdue recovery",
        )
    ]


def test_calendar_window_currently_filters_overdue_before_block_logic(
    monkeypatch,
):
    """
    Characterization of the current defect:

    assessments_in_window() begins at today, so an overdue assessment
    is removed before print_deadline_study_plan() can pass it to
    recommended_blocks_for_assessment().
    """
    today = date(2026, 9, 13)

    overdue = _assessment(
        "Overdue Quiz",
        today - timedelta(days=1),
    )
    due_today = _assessment(
        "Today Quiz",
        today,
    )
    upcoming = _assessment(
        "Upcoming Quiz",
        today + timedelta(days=3),
    )

    monkeypatch.setattr(
        academic_calendar_planner,
        "_today",
        lambda: today,
    )
    monkeypatch.setattr(
        academic_calendar_planner,
        "pending_assessments",
        lambda: [
            overdue,
            due_today,
            upcoming,
        ],
    )

    rows = academic_calendar_planner.assessments_in_window(14)
    titles = [item["title"] for item in rows]

    assert "Overdue Quiz" not in titles
    assert titles == [
        "Today Quiz",
        "Upcoming Quiz",
    ]
