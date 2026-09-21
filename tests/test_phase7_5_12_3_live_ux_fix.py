from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations


def _seed_search_database(tmp_path):
    path = tmp_path / "search.db"
    apply_migrations(path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('c-ma','MA103N','Linear Algebra','active','','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO topics "
        "(id,course_id,name,normalized_name,position,status,created_at,updated_at,deleted_at) "
        "VALUES ('t-lu','c-ma','LU Factorization','lu factorization',1,'not_started','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO resources "
        "(id,resource_type,title,canonical_uri,provider,status,quality_note,created_at,updated_at,deleted_at) "
        "VALUES ('r-lu','lecture','MIT 18.06 LU Lecture','https://example.com/lu','MIT OCW','not_started','','x','x',NULL)"
    )
    c.execute(
        "INSERT INTO resource_courses(resource_id,course_id,role) "
        "VALUES ('r-lu','c-ma','supporting')"
    )
    c.execute(
        "INSERT INTO resource_topics(resource_id,topic_id,relation_source,confidence) "
        "VALUES ('r-lu','t-lu','test',1.0)"
    )
    c.execute(
        "INSERT INTO knowledge_documents "
        "(id,kind,canonical_uri,path_key,mime_type,content_hash,size_bytes,source_timestamp,"
        "extraction_status,extraction_version,extraction_error,created_at,updated_at) "
        "VALUES ('d-lu','video_transcript','https://example.com/lu',NULL,'text/plain',"
        "?,100,NULL,'completed','v1',NULL,'x','x')",
        ("a" * 64,),
    )
    c.execute(
        "INSERT INTO resource_documents(resource_id,document_id,role) "
        "VALUES ('r-lu','d-lu','source')"
    )
    c.execute(
        "INSERT INTO knowledge_chunks "
        "(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,text_hash,"
        "extraction_version,chunk_text) VALUES "
        "('ch-lu','d-lu',0,NULL,0,48,'text',?,'v1',"
        "'LU factorization records elimination multipliers.')",
        ("b" * 64,),
    )
    c.commit()
    c.close()
    return path


def test_search_accepts_factorisation_and_falls_back_when_index_is_unavailable(tmp_path):
    from personal_learning_assistant.services.unified_search_service import (
        UnifiedSearchService,
    )

    path = _seed_search_database(tmp_path)

    class BrokenRuntime:
        def search(self, *args, **kwargs):
            raise RuntimeError("index unavailable")

    class EmptyVault:
        def workspace(self, query):
            return {"notes": ()}

    service = UnifiedSearchService(
        database_path=path,
        runtime=BrokenRuntime(),
        obsidian_workspace_factory=lambda: EmptyVault(),
    )
    results = service.search("LU FACTORISATION")

    assert len(results) == 1
    assert results[0].title == "MIT 18.06 LU Lecture"
    assert "LU Factorization" in results[0].topic_labels
    assert "Academic metadata match" in results[0].relevance_reasons
    assert service.last_warning


class _VaultConfig:
    def __init__(self, vault):
        self.vault = Path(vault)

    def load_config(self):
        return {"vault_path": str(self.vault), "enabled": True}

    def validate_vault_path(self, value):
        path = Path(value)
        return path.is_dir() and (path / ".obsidian").is_dir(), "validation"


def test_obsidian_wikilinks_resolve_and_backlinks_are_discovered(tmp_path):
    from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import (
        ObsidianWorkspaceReader,
    )
    from personal_learning_assistant.services.obsidian_markdown_renderer import (
        render_markdown,
    )
    from personal_learning_assistant.services.obsidian_workspace_service import (
        ObsidianWorkspaceService,
    )

    vault = tmp_path / "Vault"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / "Math").mkdir()
    (vault / "Math" / "LU.md").write_text(
        "# LU Factorization\n\nElimination multipliers.\n",
        encoding="utf-8",
    )
    (vault / "Index.md").write_text(
        "# Index\n\nStudy [[Math/LU|LU factorization]] next.\n",
        encoding="utf-8",
    )

    service = ObsidianWorkspaceService(_VaultConfig(vault), ObsidianWorkspaceReader)
    index = service.note_preview("Index.md")
    lu = service.note_preview("Math/LU.md")

    assert index["wikilinks"][0]["resolved_path"] == "Math/LU.md"
    assert lu["backlinks"][0]["relative_path"] == "Index.md"

    html = str(render_markdown(index["text"], wikilinks=index["wikilinks"]))
    assert "/obsidian/note?path=Math%2FLU.md" in html
    assert "LU factorization" in html


def test_calendar_can_move_between_months_and_surfaces_dated_tasks(tmp_path):
    from personal_learning_assistant.repositories.sqlite.operational_calendar_repository import (
        SQLiteOperationalCalendarRepository,
    )
    from personal_learning_assistant.services.operational_calendar_service import (
        OperationalCalendarService,
    )

    path = tmp_path / "planner.db"
    apply_migrations(path)
    c = sqlite3.connect(path)
    c.execute(
        "INSERT INTO planner_tasks "
        "(id,title,description,priority,estimated_minutes,due_on,status,manual_revision,"
        "created_at,updated_at,rollover_policy) "
        "VALUES ('task-oct','Solve LU set','','P0',45,'2026-10-05','scheduled',0,'x','x','')"
    )
    c.commit()
    c.close()

    service = OperationalCalendarService(SQLiteOperationalCalendarRepository(path))
    view = service.view(view="month", anchor_date="2026-10-15")

    assert view["previous_anchor"] == "2026-09-01"
    assert view["next_anchor"] == "2026-11-01"
    assert any(
        item["source"] == "task" and item["title"] == "Solve LU set"
        for item in view["items"]
    )


def test_planner_task_edit_route_uses_existing_service_boundary():
    from personal_learning_assistant.ui.web import create_app

    captured = {}

    class FakePlanner:
        def update_task(self, task_id, **payload):
            captured["task_id"] = task_id
            captured["payload"] = payload
            return {"id": task_id}

    app = create_app(
        {
            "TESTING": True,
            "OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY": lambda: FakePlanner(),
        }
    )
    response = app.test_client().post(
        "/planning/tasks/task-1",
        data={
            "title": "Revise LU",
            "description": "",
            "priority": "P0",
            "estimated_minutes": "60",
            "due_on": "2026-10-05",
            "preferred_day": "Monday",
            "preferred_window": "evening",
            "rollover_policy": "carry",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/planning/tasks?updated=1")
    assert captured["task_id"] == "task-1"
    assert captured["payload"]["title"] == "Revise LU"
    assert captured["payload"]["preferred_window"] == "evening"
