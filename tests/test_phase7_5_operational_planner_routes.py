from __future__ import annotations

import io


class FakePlanner:
    def __init__(self):
        self.calls = []

    def planning_home(self, today=None):
        return {
            "available": True,
            "today": "2026-10-12",
            "task_summary": {"open": 3, "p0": 1, "p1": 1, "p2": 1},
            "agenda": None,
            "today_preview": {"summary": {"scheduled_focus_minutes": 60, "fixed_count": 2}},
            "daily_review_status": "not_generated",
        }

    def tasks_workspace(self, **filters):
        return {
            "available": True,
            "tasks": (),
            "filters": filters,
            "summary": {"open": 0, "p0": 0, "p1": 0, "p2": 0},
        }

    def create_task(self, **payload):
        self.calls.append(("create_task", payload))
        return {"id": "t1"}

    def update_task(self, task_id, **payload):
        self.calls.append(("update_task", task_id, payload))
        return {"id": task_id}

    def transition_task(self, task_id, status):
        self.calls.append(("transition_task", task_id, status))
        return {"id": task_id, "status": status}

    def preview_month_plan(self, filename, payload):
        self.calls.append(("preview", filename, payload))
        return {
            "valid": True,
            "source_sha256": "a" * 64,
            "plan": {
                "title": "October",
                "starts_on": "2026-10-01",
                "ends_on": "2026-10-31",
                "timezone": "Asia/Kolkata",
            },
            "counts": {
                "days": 31,
                "assessments": 5,
                "fixed_and_class_events": 10,
                "personal_routines": 4,
                "tasks": 8,
                "weekly_reviews": 5,
            },
            "waiting_exam_slots": ("a1",),
            "warnings": (),
            "errors": (),
            "already_imported": False,
        }

    def approve_month_plan(self, filename, payload, expected_sha256):
        self.calls.append(("approve", filename, expected_sha256))
        return {"created": True}

    def calendar_view(self, *, view="month", anchor_date=None):
        return {
            "available": True,
            "view": view,
            "anchor_date": anchor_date or "2026-10-12",
            "starts_on": "2026-10-01",
            "ends_on": "2026-10-31",
            "items": (),
            "days": {},
            "waiting_exam_slots": (),
        }

    def schedule_assessment(self, assessment_id, **payload):
        self.calls.append(("schedule_assessment", assessment_id, payload))
        return {"assessment_id": assessment_id}

    def day_view(self, agenda_date):
        return {
            "available": True,
            "date": agenda_date,
            "existing": None,
            "day_mode": "normal",
            "items": (),
            "fixed": (),
            "tasks": (),
            "study": (),
            "summary": {
                "fixed_count": 0, "task_count": 0,
                "scheduled_focus_minutes": 0, "p0": 0,
            },
        }

    def generate_day(self, agenda_date):
        self.calls.append(("generate_day", agenda_date))
        return {"status": "draft"}

    def approve_day(self, agenda_date):
        self.calls.append(("approve_day", agenda_date))
        return {"status": "approved"}

    def update_day_item(self, agenda_date, item_id, *, status, actual_minutes=None):
        self.calls.append(("update_item", agenda_date, item_id, status, actual_minutes))
        return {}

    def close_day(self, agenda_date, review):
        self.calls.append(("close_day", agenda_date, review))
        return {}

    def weekly_review(self, anchor_date):
        return {
            "available": True,
            "week_start": "2026-10-12",
            "week_end": "2026-10-18",
            "evidence": {
                "planned_items": 1, "completed_items": 1,
                "planned_focus_minutes": 60, "actual_focus_minutes": 55,
                "carry_forward_count": 0, "missed_deadline_count": 0,
            },
            "review": None,
        }

    def save_weekly_review(self, anchor_date, payload, *, close=False):
        self.calls.append(("weekly", anchor_date, close))
        return {}


def _app(fake):
    from personal_learning_assistant.ui.web import create_app
    return create_app({
        "TESTING": True,
        "OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY": lambda: fake,
        "PLANNING_DASHBOARD_PROVIDER": lambda: {
            "available": True,
            "message": "",
            "summary": {
                "courses": 0, "average_progress": 0, "mastered_topics": 0,
                "weak_topics": 0, "missing_topics": 0, "saved_plans": 0,
            },
            "courses": [],
            "plans": [],
        },
        "CALENDAR_GRADES_PROVIDER": lambda: {
            "available": True,
            "message": "",
            "date": "2026-10-12",
            "summary": {
                "calendar_events": 0, "overdue": 0, "upcoming": 0,
                "grade_courses": 0, "recorded_grades": 0,
            },
            "calendar": {
                "window_days": 30,
                "groups": {"overdue": [], "upcoming": [], "later": [], "completed": []},
            },
            "grades": {
                "source_present": False,
                "semester_name": "",
                "target_sgpa": None,
                "scale": {"source": "", "verified": False, "bands": []},
                "courses": [],
                "semester_result": None,
            },
        },
    })


def test_operational_get_routes_are_readable_and_side_effect_free():
    fake = FakePlanner()
    client = _app(fake).test_client()
    for path in (
        "/planning/tasks",
        "/planning/month-plan",
        "/planning/day/2026-10-12",
        "/planning/review/week/2026-10-18",
        "/calendar?view=month&date=2026-10-12",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
    assert fake.calls == []


def test_task_create_uses_post_prg():
    fake = FakePlanner()
    response = _app(fake).test_client().post(
        "/planning/tasks",
        data={"title": "New task", "priority": "P1", "estimated_minutes": "45"},
    )
    assert response.status_code == 303
    assert fake.calls[0][0] == "create_task"


def test_month_preview_is_post_but_not_approval():
    fake = FakePlanner()
    response = _app(fake).test_client().post(
        "/planning/month-plan/preview",
        data={"plan_file": (io.BytesIO(b"schema_version: test"), "plan.yaml")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "Import preview" in text
    assert [call[0] for call in fake.calls] == ["preview"]


def test_month_approval_uses_expected_hash_and_prg():
    fake = FakePlanner()
    response = _app(fake).test_client().post(
        "/planning/month-plan/approve",
        data={
            "expected_sha256": "a" * 64,
            "plan_file": (io.BytesIO(b"same"), "plan.yaml"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 303
    assert fake.calls[0][0] == "approve"


def test_day_commands_use_explicit_post_and_prg():
    fake = FakePlanner()
    client = _app(fake).test_client()
    for path, data in (
        ("/planning/day/2026-10-12/generate", {}),
        ("/planning/day/2026-10-12/approve", {}),
        ("/planning/day/2026-10-12/items/i1", {"status": "completed", "actual_minutes": "40"}),
        ("/planning/day/2026-10-12/close", {"learned": "x"}),
    ):
        assert client.post(path, data=data).status_code == 303


def test_calendar_confirmed_assessment_slot_is_explicit_post():
    fake = FakePlanner()
    response = _app(fake).test_client().post(
        "/calendar/assessments/a1/schedule",
        data={
            "due_on": "2026-10-08",
            "start_time": "09:00",
            "end_time": "10:00",
            "venue": "Room 1",
        },
    )
    assert response.status_code == 303
    assert fake.calls[0][0] == "schedule_assessment"
