from __future__ import annotations

from pathlib import Path

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesRepository,
)
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService


NOWS = iter(
    (
        "2026-09-26T10:00:00Z",
        "2026-09-26T10:01:00Z",
        "2026-09-26T10:02:00Z",
        "2026-09-26T10:03:00Z",
    )
)


def _service(tmp_path):
    repo = AnvayaNotesRepository(
        notes_path=tmp_path / "notes.json",
        assets_root=tmp_path / "assets",
    )
    return AnvayaNotesService(repo, now=lambda: next(NOWS)), repo


def test_notes_companion_add_and_archive_are_note_local(tmp_path):
    service, repo = _service(tmp_path)
    created = service.create_typed_note({"title": "LU", "body": "A=LU"})
    first = repo.get_note(created["id"])

    service.add_companion_entry(
        created["id"],
        kind="saved_note",
        text="L stores elimination multipliers.",
        expected_updated_at=first["updated_at"],
    )
    second = repo.get_note(created["id"])
    service.add_companion_entry(
        created["id"],
        kind="doubt",
        text="Why is pivoting needed?",
        expected_updated_at=second["updated_at"],
    )

    reader = service.reader(created["id"])
    assert reader["companion"]["saved_count"] == 1
    assert reader["companion"]["doubt_count"] == 1
    assert reader["companion"]["saved_notes"][0]["text"].startswith("L stores")

    entry_id = reader["companion"]["saved_notes"][0]["id"]
    service.archive_companion_entry(
        created["id"],
        entry_id=entry_id,
        expected_updated_at=repo.get_note(created["id"])["updated_at"],
    )
    after = service.reader(created["id"])
    assert after["companion"]["saved_count"] == 0
    assert after["companion"]["doubt_count"] == 1


def test_notes_analysis_counts_types_courses_media_and_companion(tmp_path):
    service, repo = _service(tmp_path)
    typed = service.create_typed_note(
        {"title": "Vectors", "course": "MA103N", "body": "Body"}
    )
    service.create_handwritten_note(
        {"title": "AAS", "course": "CY100N"},
        [("page.pdf", b"%PDF-1.4\n%%EOF")],
    )
    row = repo.get_note(typed["id"])
    service.add_companion_entry(
        typed["id"],
        kind="doubt",
        text="Basis versus span?",
        expected_updated_at=row["updated_at"],
    )

    analysis = service.analysis()
    assert analysis["summary"]["total"] == 2
    assert analysis["summary"]["typed"] == 1
    assert analysis["summary"]["handwritten"] == 1
    assert analysis["summary"]["doubts"] == 1
    assert analysis["summary"]["media"] == 1
    assert {row["course"] for row in analysis["courses"]} == {"MA103N", "CY100N"}


def test_desktop_navigation_is_collapsible_and_persisted():
    root = Path(__file__).resolve().parents[1]
    base = (root / "personal_learning_assistant/ui/web/templates/base.html").read_text(encoding="utf-8")
    js = (root / "personal_learning_assistant/ui/web/static/js/app.js").read_text(encoding="utf-8")
    css = (root / "personal_learning_assistant/ui/web/static/css/app.css").read_text(encoding="utf-8")

    assert 'id="nav-toggle"' in base
    assert "sidebar-collapsed" in js
    assert "anvaya.sidebar.collapsed" in js
    assert "body.sidebar-collapsed .app-shell" in css
    assert "grid-template-columns: 0 minmax(0, 1fr)" in css


def test_notes_reader_uses_compact_draggable_study_tools():
    root = Path(__file__).resolve().parents[1]
    reader = (root / "personal_learning_assistant/ui/web/templates/anvaya_notes_reader.html").read_text(encoding="utf-8")
    tools = (root / "personal_learning_assistant/ui/web/templates/_anvaya_notes_study_tools.html").read_text(encoding="utf-8")
    js = (root / "personal_learning_assistant/ui/web/static/js/anvaya_notes_reader.js").read_text(encoding="utf-8")

    assert "_anvaya_notes_study_tools.html" in reader
    assert "Saved notes" in tools
    assert "Doubts" in tools
    assert "pointermove" in js
    assert "anvaya.notes.studyTools.position" in js


def test_home_hides_detailed_risk_and_priority_panels():
    root = Path(__file__).resolve().parents[1]
    home = (root / "personal_learning_assistant/ui/web/templates/home.html").read_text(encoding="utf-8")
    assert "Check your analysis" in home
    assert 'id="priorities-heading"' not in home
    assert 'id="risk-heading"' not in home
    assert "Open Analysis Hub" in home


def test_analysis_page_contains_visualizations():
    root = Path(__file__).resolve().parents[1]
    analysis = (root / "personal_learning_assistant/ui/web/templates/analysis.html").read_text(encoding="utf-8")
    css = (root / "personal_learning_assistant/ui/web/static/css/app.css").read_text(encoding="utf-8")
    for token in (
        "Analysis Hub",
        "Typed vs handwritten",
        "Scheduled minutes by course",
        "Priority topics",
        "Academic risk signals",
        "Notes by course",
        "Saved thinking",
    ):
        assert token in analysis
    assert "analysis-donut" in analysis
    assert ".analysis-donut" in css
    assert ".analysis-bar-track" in css


class _FakeNotes:
    def analysis(self):
        return {
            "available": True,
            "summary": {
                "total": 4,
                "typed": 3,
                "handwritten": 1,
                "saved_notes": 2,
                "doubts": 1,
                "media": 5,
                "inline_media": 2,
            },
            "type_percent": {"typed": 75.0, "handwritten": 25.0},
            "courses": [{"course": "MA103N", "count": 2, "percent": 50.0}],
        }


def _academic():
    return {
        "available": True,
        "message": "",
        "date": "2026-09-26",
        "summary": {
            "urgent_deadlines": 1,
            "scheduled_minutes": 90,
            "priority_topics": 1,
            "risk_courses": 1,
        },
        "deadlines": [
            {
                "course_code": "MA103N",
                "title": "Mid-sem",
                "due_label": "in 9 days",
                "weightage_percent": 25,
            }
        ],
        "study_blocks": [
            {
                "course_code": "MA103N",
                "title": "Revision",
                "minutes": 90,
                "label": "Study block",
                "due_label": "today",
            }
        ],
        "priorities": [
            {
                "course_code": "MA103N",
                "topic": "LU",
                "score": 8.0,
                "reasons": ["weak evidence"],
                "performance": {"accuracy": 60, "attempts": 5},
            }
        ],
        "risks": [
            {
                "course_code": "MA103N",
                "course_name": "Linear Algebra",
                "score": 6.0,
                "weak_topics": ["LU"],
                "evidence_topics": ["systems"],
                "urgent_count": 1,
            }
        ],
        "best_next_action": None,
    }


def test_analysis_route_is_explicit_and_read_only():
    from personal_learning_assistant.ui.web import create_app

    app = create_app(
        {
            "TESTING": True,
            "HOME_DASHBOARD_PROVIDER": _academic,
            "ANVAYA_NOTES_SERVICE_FACTORY": lambda: _FakeNotes(),
        }
    )
    response = app.test_client().get("/analysis")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Analysis Hub" in html
    assert "75.0%" in html
    assert "MA103N" in html
    assert "LU" in html
