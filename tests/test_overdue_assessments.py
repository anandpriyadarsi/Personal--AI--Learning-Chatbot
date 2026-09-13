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
    Regression protection: the study-block engine knows how
    to handle an overdue assessment if the assessment reaches it.
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


def test_future_calendar_window_still_excludes_overdue(monkeypatch):
    """
    Regression protection for Fix 3 + Fix 4 together:

    normal calendar windows remain future-facing and half-open.
    Overdue work is handled by the recovery/study-plan path,
    not mixed into the normal 14-day window.
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


def test_deadline_study_plan_source_includes_overdue_for_recovery(
    monkeypatch,
):
    """
    Regression test for the overdue filtering defect.

    The old print_deadline_study_plan() path used
    assessments_in_window(14), so overdue assessments were
    filtered out before recovery blocks could be generated.
    The fixed source includes overdue items separately.
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

    rows = (
        academic_calendar_planner
        .assessments_for_deadline_study_plan(14)
    )
    titles = [item["title"] for item in rows]

    assert titles == [
        "Overdue Quiz",
        "Today Quiz",
        "Upcoming Quiz",
    ]

    overdue_blocks = (
        academic_calendar_planner
        .recommended_blocks_for_assessment(overdue)
    )

    assert overdue_blocks == [
        (
            today,
            90,
            "Immediate overdue recovery",
        )
    ]
