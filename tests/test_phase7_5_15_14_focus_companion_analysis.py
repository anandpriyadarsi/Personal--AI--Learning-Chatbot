from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesConflictError,
    AnvayaNotesRepository,
)
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesService


def _service(tmp_path):
    repo = AnvayaNotesRepository(
        notes_path=tmp_path / "notes.json",
        assets_root=tmp_path / "assets",
    )
    counter = {"value": 0}

    def now():
        counter["value"] += 1
        return "2026-09-26T10:{:02d}:00Z".format(counter["value"])

    return AnvayaNotesService(repo, now=now), repo


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


def test_notes_companion_rejects_stale_writes_without_changing_note_or_vault(tmp_path):
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    original = vault / "LU.md"
    original.write_text("# Original vault content", encoding="utf-8")
    service, repo = _service(tmp_path)
    created = service.create_typed_note({"title": "LU", "body": "A = LU"})
    stale_time = repo.get_note(created["id"])["updated_at"]

    service.add_companion_entry(
        created["id"], kind="saved_note", text="Pivot", expected_updated_at=stale_time
    )
    before_conflict = repo.get_note(created["id"])
    with pytest.raises(AnvayaNotesConflictError):
        service.add_companion_entry(
            created["id"], kind="doubt", text="Why pivot?", expected_updated_at=stale_time
        )

    assert repo.get_note(created["id"]) == before_conflict
    assert original.read_text(encoding="utf-8") == "# Original vault content"
    assert service.reader(created["id"])["companion"]["doubt_count"] == 0


def test_simultaneous_companion_posts_cannot_overwrite_one_another(tmp_path):
    service, repo = _service(tmp_path)
    note_id = service.create_typed_note({"title": "Concurrent", "body": "Body"})["id"]
    expected = repo.get_note(note_id)["updated_at"]
    other_repo = AnvayaNotesRepository(notes_path=repo.notes_path, assets_root=repo.assets_root)
    other = AnvayaNotesService(other_repo, now=lambda: "2026-09-26T11:00:00Z")
    first_saving, second_started, second_saving, release = Event(), Event(), Event(), Event()
    first_save = repo._save
    second_save = other_repo._save
    second_update = other_repo.update_note

    def pause_first(rows):
        first_saving.set()
        assert release.wait(3)
        return first_save(rows)

    def observe_second(rows):
        second_saving.set()
        return second_save(rows)

    def start_second(*args, **kwargs):
        second_started.set()
        return second_update(*args, **kwargs)

    repo._save = pause_first
    other_repo._save = observe_second
    other_repo.update_note = start_second
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.add_companion_entry, note_id,
                            kind="saved_note", text="first", expected_updated_at=expected)
        assert first_saving.wait(3)
        second = pool.submit(other.add_companion_entry, note_id,
                             kind="doubt", text="second", expected_updated_at=expected)
        try:
            assert second_started.wait(3)
            assert not second_saving.wait(0.2), "Concurrent writes passed the same version check"
        finally:
            release.set()
        assert first.result(timeout=3)["id"] == note_id
        with pytest.raises(AnvayaNotesConflictError):
            second.result(timeout=3)
    after = repo.get_note(note_id)["companion"]
    assert [entry["text"] for entry in after["saved_notes"]] == ["first"]
    assert after["doubts"] == []


def test_fixed_clock_still_advances_companion_version(tmp_path):
    repo = AnvayaNotesRepository(notes_path=tmp_path / "notes.json", assets_root=tmp_path / "assets")
    service = AnvayaNotesService(repo, now=lambda: "2026-09-26T10:00:00Z")
    note_id = service.create_typed_note({"title": "Clock", "body": "Body"})["id"]
    old_version = repo.get_note(note_id)["updated_at"]
    service.add_companion_entry(note_id, kind="saved_note", text="first",
                                expected_updated_at=old_version)
    assert repo.get_note(note_id)["updated_at"] != old_version
    with pytest.raises(AnvayaNotesConflictError):
        service.add_companion_entry(note_id, kind="doubt", text="stale",
                                    expected_updated_at=old_version)


def test_legacy_note_without_companion_still_reads_and_accepts_study_tools(tmp_path):
    service, repo = _service(tmp_path)
    created = service.create_typed_note({"title": "Old", "body": "Body"})
    legacy = repo.get_note(created["id"])
    legacy.pop("companion", None)
    repo.notes_path.write_text(json.dumps([legacy]), encoding="utf-8")

    assert service.reader(created["id"])["companion"]["saved_count"] == 0
    service.add_companion_entry(
        created["id"], kind="doubt", text="Old doubt", expected_updated_at=legacy["updated_at"]
    )
    assert service.reader(created["id"])["companion"]["doubt_count"] == 1


def test_study_tools_forms_write_to_native_note_and_render_current_entries(tmp_path):
    from personal_learning_assistant.ui.web import create_app

    service, repo = _service(tmp_path)
    created = service.create_typed_note({"title": "LU", "body": "A = LU"})
    note_id = created["id"]
    app = create_app({"TESTING": True, "ANVAYA_NOTES_SERVICE_FACTORY": lambda: service})
    client = app.test_client()
    reader_url = "/notes/view/{}".format(note_id)
    before = repo.get_note(note_id)

    response = client.post(
        reader_url + "/companion",
        data={
            "kind": "doubt", "entry_text": "When is pivoting needed?",
            "expected_updated_at": before["updated_at"],
        },
    )

    assert response.status_code == 303
    assert response.location.endswith("?study_tools=1&study_tab=doubts")
    html = client.get(reader_url).get_data(as_text=True)
    assert "When is pivoting needed?" in html
    assert 'id="notes-study-tools-launcher"' in html
    assert repo.get_note(note_id)["companion"]["doubts"][0]["archived_at"] == ""
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.json"]


def test_notes_companion_redirects_keep_saved_and_doubt_tabs(tmp_path):
    from personal_learning_assistant.ui.web import create_app

    service, repo = _service(tmp_path)
    note_id = service.create_typed_note({"title": "Tabs", "body": "Body"})["id"]
    client = create_app({
        "TESTING": True, "ANVAYA_NOTES_SERVICE_FACTORY": lambda: service
    }).test_client()
    url = f"/notes/view/{note_id}"

    for kind, tab in (("saved_note", "saved"), ("doubt", "doubts")):
        result = client.post(url + "/companion", data={
            "kind": kind, "entry_text": f"{kind} text",
            "expected_updated_at": repo.get_note(note_id)["updated_at"],
        })
        assert result.location.endswith(f"?study_tools=1&study_tab={tab}")
        html = client.get(url).get_data(as_text=True)
        assert f'name="study_tab" value="{tab}"' in html
        key = "saved_notes" if tab == "saved" else "doubts"
        entry_id = repo.get_note(note_id)["companion"][key][-1]["id"]
        archived = client.post(url + f"/companion/{entry_id}/archive", data={
            "expected_updated_at": repo.get_note(note_id)["updated_at"],
            "study_tab": tab,
        })
        assert archived.location.endswith(f"?study_tools=1&study_tab={tab}")

    html = client.get(url).get_data(as_text=True)
    assert "<noscript>" in html


def test_study_tools_forms_protect_stale_note_and_archive_without_deletion(tmp_path):
    from personal_learning_assistant.ui.web import create_app

    service, repo = _service(tmp_path)
    created = service.create_typed_note({"title": "Rank", "body": "rank(A)"})
    note_id = created["id"]
    reader_url = "/notes/view/{}".format(note_id)
    client = create_app({
        "TESTING": True, "ANVAYA_NOTES_SERVICE_FACTORY": lambda: service
    }).test_client()
    stale = repo.get_note(note_id)["updated_at"]
    assert client.post(reader_url + "/companion", data={
        "kind": "saved_note", "entry_text": "Rank counts pivots",
        "expected_updated_at": stale,
    }).status_code == 303
    first = repo.get_note(note_id)

    assert client.post(reader_url + "/companion", data={
        "kind": "doubt", "entry_text": "Why?", "expected_updated_at": stale,
    }).status_code == 409
    assert repo.get_note(note_id) == first

    entry_id = first["companion"]["saved_notes"][0]["id"]
    response = client.post(
        reader_url + "/companion/{}/archive".format(entry_id),
        data={"expected_updated_at": first["updated_at"]},
    )
    assert response.status_code == 303
    archived = repo.get_note(note_id)["companion"]["saved_notes"][0]
    assert archived["id"] == entry_id
    assert archived["archived_at"]
    assert service.reader(note_id)["companion"]["saved_count"] == 0


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


def test_analysis_shows_all_study_blocks_after_home_preview_limit():
    from personal_learning_assistant.services.home_dashboard_service import (
        build_home_dashboard_from_brief,
    )
    from personal_learning_assistant.ui.web import create_app
    from tests.test_phase7_5_home_dashboard import _fake_brief

    brief = _fake_brief()
    blocks = brief._today_blocks() + [
        {"assessment": {"course_id": "c3", "title": "Extra"},
         "minutes": 10, "label": "Extra"}
        for _ in range(6)
    ]
    brief._today_blocks = lambda: blocks
    brief._course_code = lambda item: "NEW101" if item.get("course_id") == "c3" else "MA103N"
    dashboard = build_home_dashboard_from_brief(brief)

    assert len(dashboard["study_blocks"]) == 6
    assert dashboard["summary"]["scheduled_minutes"] == 135
    assert dashboard["study_minutes_by_course"] == {"MA103N": 75, "NEW101": 60}
    app = create_app({
        "TESTING": True, "HOME_DASHBOARD_PROVIDER": lambda: dashboard,
        "ANVAYA_NOTES_SERVICE_FACTORY": lambda: _FakeNotes(),
    })
    html = app.test_client().get("/analysis").get_data(as_text=True)
    assert "NEW101" in html
    assert "60 min" in html


def test_analysis_marks_unreadable_notes_unavailable_without_zero_counts():
    from personal_learning_assistant.services.anvaya_notes_service import (
        AnvayaNotesUnavailableError,
    )
    from personal_learning_assistant.ui.web import create_app

    class BrokenNotes:
        def analysis(self):
            raise AnvayaNotesUnavailableError("PRIVATE PATH")

    app = create_app({
        "TESTING": True, "HOME_DASHBOARD_PROVIDER": _academic,
        "ANVAYA_NOTES_SERVICE_FACTORY": lambda: BrokenNotes(),
    })
    html = app.test_client().get("/analysis").get_data(as_text=True)
    assert "Notes analysis is temporarily unavailable" in html
    assert "PRIVATE PATH" not in html
    assert html.count("Notes data unavailable") >= 4
    assert "Create personal Notes to see subject distribution." not in html
    assert "0 percent typed notes" not in html
