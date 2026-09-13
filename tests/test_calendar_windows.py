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


def test_seven_day_window_currently_includes_eighth_calendar_date(monkeypatch):
    """
    Characterization test for the current inclusive-end defect.

    A nominal 7-day window beginning on day 0 should eventually mean
    day offsets 0..6. The current implementation also includes offset 7,
    so this test records that existing behavior before we fix it.
    """
    today = date(2026, 9, 13)

    monkeypatch.setattr(
        academic_calendar_planner,
        "_today",
        lambda: today,
    )

    items = [
        _assessment("Today Quiz", today),
        _assessment("Day 6 Quiz", today + timedelta(days=6)),
        _assessment("Day 7 Quiz", today + timedelta(days=7)),
        _assessment("Day 8 Quiz", today + timedelta(days=8)),
    ]

    monkeypatch.setattr(
        academic_calendar_planner,
        "pending_assessments",
        lambda: items,
    )

    rows = academic_calendar_planner.assessments_in_window(7)
    titles = [item["title"] for item in rows]

    assert titles == [
        "Today Quiz",
        "Day 6 Quiz",
        "Day 7 Quiz",
    ]
    assert len(rows) == 3


def test_thirty_day_window_currently_includes_31st_calendar_date(monkeypatch):
    """
    Characterization test for the same defect in the 30-day view.

    The current implementation includes offsets 0..30, which spans
    31 calendar dates.
    """
    today = date(2026, 9, 13)

    monkeypatch.setattr(
        academic_calendar_planner,
        "_today",
        lambda: today,
    )

    items = [
        _assessment("Today Assignment", today),
        _assessment("Day 29 Assignment", today + timedelta(days=29)),
        _assessment("Day 30 Assignment", today + timedelta(days=30)),
        _assessment("Day 31 Assignment", today + timedelta(days=31)),
    ]

    monkeypatch.setattr(
        academic_calendar_planner,
        "pending_assessments",
        lambda: items,
    )

    rows = academic_calendar_planner.assessments_in_window(30)
    titles = [item["title"] for item in rows]

    assert titles == [
        "Today Assignment",
        "Day 29 Assignment",
        "Day 30 Assignment",
    ]
    assert len(rows) == 3
