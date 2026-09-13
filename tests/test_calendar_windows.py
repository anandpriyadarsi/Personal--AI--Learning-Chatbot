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


def test_seven_day_window_contains_exactly_seven_calendar_dates(monkeypatch):
    """
    Regression test for the old inclusive-end defect.

    A 7-day window beginning today must include day offsets 0..6.
    Offset 7 belongs outside this view.
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
    ]
    assert "Day 7 Quiz" not in titles
    assert len(rows) == 2


def test_thirty_day_window_contains_exactly_thirty_calendar_dates(monkeypatch):
    """
    Regression test for the same defect in the 30-day view.

    A 30-day window beginning today must include day offsets 0..29.
    Offset 30 belongs outside this view.
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
    ]
    assert "Day 30 Assignment" not in titles
    assert len(rows) == 2
