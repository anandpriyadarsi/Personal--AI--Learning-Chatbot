import multi_course_planner


def test_two_course_120_minute_plan_currently_allocates_only_108(monkeypatch):
    """
    Characterization test for the current V9.2 allocation defect.

    With two equally urgent courses and 120 requested minutes,
    MAX_COURSE_SHARE = 0.45 caps each course at 54 minutes.
    The allocator cannot distribute the remaining 12 minutes,
    so the current implementation returns only 108 minutes.
    """

    courses = [
        {
            "id": "course-a",
            "code": "A",
            "name": "Course A",
        },
        {
            "id": "course-b",
            "code": "B",
            "name": "Course B",
        },
    ]

    def fake_course_urgency(course):
        return 100.0, []

    monkeypatch.setattr(
        multi_course_planner,
        "course_urgency",
        fake_course_urgency,
    )

    allocations = multi_course_planner.bounded_course_allocations(
        courses,
        120,
    )

    allocated_minutes = [
        item["minutes"]
        for item in allocations
    ]

    assert allocated_minutes == [54, 54]
    assert sum(allocated_minutes) == 108
    assert sum(allocated_minutes) != 120


def test_two_course_allocation_cap_is_45_percent():
    assert multi_course_planner.MAX_COURSE_SHARE == 0.45
