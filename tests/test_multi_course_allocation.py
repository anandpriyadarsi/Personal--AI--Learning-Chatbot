import multi_course_planner


def _courses(count):
    return [
        {
            "id": f"course-{index}",
            "code": f"C{index}",
            "name": f"Course {index}",
        }
        for index in range(1, count + 1)
    ]


def test_two_course_120_minute_plan_allocates_all_requested_minutes(monkeypatch):
    """
    Regression test for the old V9.2 allocation defect.

    Earlier, two equal courses with 120 requested minutes produced
    only 54 + 54 = 108 minutes because MAX_COURSE_SHARE blocked
    redistribution. The fixed allocator must preserve all 120.
    """

    def fake_course_urgency(course):
        return 100.0, []

    monkeypatch.setattr(
        multi_course_planner,
        "course_urgency",
        fake_course_urgency,
    )

    allocations = multi_course_planner.bounded_course_allocations(
        _courses(2),
        120,
    )

    allocated_minutes = [
        item["minutes"]
        for item in allocations
    ]

    assert len(allocated_minutes) == 2
    assert allocated_minutes == [60, 60]
    assert all(
        minutes > 0
        for minutes in allocated_minutes
    )
    assert sum(allocated_minutes) == 120


def test_requested_minutes_are_never_lost_with_three_courses(monkeypatch):
    requested_minutes = 175

    urgency_by_course = {
        "course-1": 90.0,
        "course-2": 45.0,
        "course-3": 15.0,
    }

    def fake_course_urgency(course):
        return urgency_by_course[course["id"]], []

    monkeypatch.setattr(
        multi_course_planner,
        "course_urgency",
        fake_course_urgency,
    )

    allocations = multi_course_planner.bounded_course_allocations(
        _courses(3),
        requested_minutes,
    )

    allocated_minutes = [
        item["minutes"]
        for item in allocations
    ]

    assert len(allocated_minutes) == 3
    assert all(
        minutes > 0
        for minutes in allocated_minutes
    )
    assert sum(allocated_minutes) == requested_minutes


def test_two_course_allocation_cap_constant_is_preserved():
    assert multi_course_planner.MAX_COURSE_SHARE == 0.45
