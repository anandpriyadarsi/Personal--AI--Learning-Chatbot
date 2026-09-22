from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def copied_learning_database_path(tmp_path):
    source = ROOT / "data" / "learning_assistant.db"
    assert source.is_file(), "production learning_assistant.db is required for Phase 7.5.9 tests"
    target = tmp_path / "learning_assistant.db"
    shutil.copy2(source, target)
    return target


def open_database(path):
    connection = sqlite3.connect(str(path), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def first_course_id(connection):
    row = connection.execute(
        "SELECT id FROM courses WHERE deleted_at IS NULL ORDER BY code, id LIMIT 1"
    ).fetchone()
    assert row is not None
    return str(row[0])


def first_course(connection):
    row = connection.execute(
        "SELECT id,code,name FROM courses WHERE deleted_at IS NULL ORDER BY code,id LIMIT 1"
    ).fetchone()
    assert row is not None
    return {"id": str(row[0]), "code": str(row[1]), "name": str(row[2])}


def sequential_id_factory():
    counter = itertools.count(1)
    return lambda prefix: "{}-{}".format(prefix, next(counter))


def table_counts(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return {
        str(row[0]): int(connection.execute('SELECT COUNT(*) FROM "{}"'.format(row[0])).fetchone()[0])
        for row in rows
    }


def changed_tables(before, after):
    return {name for name in set(before) | set(after) if before.get(name) != after.get(name)}


def deterministic_course_loader(course):
    def load():
        return {
            "available": True,
            "message": "",
            "courses": [
                {
                    "id": course["id"],
                    "code": course["code"],
                    "name": course["name"],
                    "semester": "",
                    "status": "active",
                    "status_label": "Active",
                    "is_active": True,
                    "topic_count": 0,
                    "mastered_count": 0,
                    "progress_percent": 0,
                    "topics": [],
                }
            ],
        }
    return load


class FakeProvider:
    def __init__(self, *, configured=True, response=None):
        self.configured = configured
        self.response = response
        self.calls = 0

    def complete(self, request):
        from personal_learning_assistant.domain.tutor_models import TutorProviderResponse

        self.calls += 1
        return TutorProviderResponse(
            content=self.response or "The retrieved source supports this explanation. [S1]",
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="fake-request-1",
        )


class FakeRetrieval:
    def __init__(self, hits=()):
        self.hits = tuple(hits)
        self.calls = 0

    def search(self, query, **kwargs):
        self.calls += 1
        return self.hits


def first_retrieval_hit(connection):
    from personal_learning_assistant.domain.retrieval_models import RetrievalHit

    row = connection.execute(
        "SELECT id,document_id,page_number,chunk_text FROM knowledge_chunks "
        "WHERE chunk_text IS NOT NULL AND TRIM(chunk_text) <> '' "
        "ORDER BY document_id,ordinal,id LIMIT 1"
    ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT id,document_id,page_number,chunk_text FROM knowledge_chunks ORDER BY document_id,ordinal,id LIMIT 1"
        ).fetchone()
    assert row is not None, "Phase 7.5.9 grounded test requires at least one knowledge chunk"
    text = str(row[3] or "Grounded project evidence for the tutor test.")
    return RetrievalHit(
        chunk_id=str(row[0]),
        document_id=str(row[1]),
        text=text,
        score=0.9,
        lexical_rank=1,
        semantic_rank=None,
        page_number=None if row[2] is None else int(row[2]),
        locator={"topic": "Grounded test evidence"},
        resource_ids=(),
        course_ids=(),
        topic_ids=(),
        providers=(),
    )


def build_test_web_service(tmp_path, *, provider=None, hits=()):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService

    database_path = copied_learning_database_path(tmp_path)
    connection = open_database(database_path)
    try:
        course = first_course(connection)
    finally:
        connection.close()
    provider = provider or FakeProvider(configured=False)
    retrieval = FakeRetrieval(hits)
    service = AcademicAgentWebService(
        database_path=database_path,
        index_root=tmp_path / "retrieval",
        course_catalogue_loader=deterministic_course_loader(course),
        provider_factory=lambda: provider,
        retrieval_service_factory=lambda _root: retrieval,
    )
    return service, database_path, course, provider, retrieval


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_hashes(path):
    root = Path(path)
    if not root.exists():
        return {}
    return {
        str(item.relative_to(root)).replace("\\", "/"): file_hash(item)
        for item in sorted(root.rglob("*"))
        if item.is_file()
    }


def test_tutor_repository_lists_recent_sessions_newest_first(tmp_path):
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService

    connection = open_database(copied_learning_database_path(tmp_path))
    # This repository-ordering test must be isolated from Anand's real Tutor
    # history copied with the production database fixture.
    connection.execute("DELETE FROM tutor_feedback")
    connection.execute("DELETE FROM tutor_evidence_links")
    connection.execute("DELETE FROM tutor_turns")
    connection.execute("DELETE FROM tutor_sessions")
    repo = SQLiteTutorRepository(connection)
    service = TutorSessionService(
        repo,
        now=iter([
            "2026-09-17T08:00:00Z",
            "2026-09-17T09:00:00Z",
            "2026-09-17T10:00:00Z",
        ]).__next__,
        id_factory=sequential_id_factory(),
    )
    course_id = first_course_id(connection)
    first = service.create_session(TutorSessionSpec(mode="concept", source_policy="source_only", course_id=course_id, title="First"))
    second = service.create_session(TutorSessionSpec(mode="doubt", source_policy="source_only", course_id=course_id, title="Second"))
    third = service.create_session(TutorSessionSpec(mode="exam", source_policy="source_first", course_id=course_id, title="Third"))
    rows = repo.list_sessions(limit=2)
    assert [row.session_id for row in rows] == [third.session_id, second.session_id]
    assert first.session_id not in [row.session_id for row in rows]
    connection.close()


def test_tutor_repository_rejects_unbounded_session_limit(tmp_path):
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository

    connection = open_database(copied_learning_database_path(tmp_path))
    repo = SQLiteTutorRepository(connection)
    with pytest.raises(ValueError, match="between 1 and 100"):
        repo.list_sessions(limit=101)
    with pytest.raises(ValueError, match="between 1 and 100"):
        repo.list_sessions(limit=0)
    connection.close()


def test_web_service_module_is_lazy_at_import(tmp_path):
    code = """
import sys
import personal_learning_assistant.services.academic_agent_web_service
for name in (
    'personal_learning_assistant.services.grounded_tutor_service',
    'personal_learning_assistant.services.adaptive_mentor_service',
    'personal_learning_assistant.retrieval.index_store',
    'personal_learning_assistant.tutor.http_provider',
):
    assert name not in sys.modules, name
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_workspace_lists_courses_sessions_and_provider_status(tmp_path):
    service, _path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    view = service.workspace("")
    assert set(view) == {
        "available", "message", "provider_configured", "courses",
        "selected_course_code", "mentor", "sessions", "modes", "source_policies",
    }
    assert view["available"] is True
    assert view["provider_configured"] is False
    assert view["courses"][0]["id"] == course["id"]
    assert isinstance(view["sessions"], list)
    assert view["mentor"] is None
    assert view["modes"] == ["concept", "doubt", "summary", "exam", "lecture", "revision", "guidance", "free"]
    assert view["source_policies"] == ["source_only", "source_first"]


def test_workspace_unknown_course_is_safe_and_does_not_call_provider_complete(tmp_path):
    provider = FakeProvider(configured=True)
    service, _path, _course, provider, _retrieval = build_test_web_service(tmp_path, provider=provider)
    view = service.workspace("NOT-A-COURSE")
    assert view["available"] is True
    assert view["mentor"] is None
    assert "not found" in view["message"].lower()
    assert provider.calls == 0


def test_create_session_defaults_to_source_only_and_reopens(tmp_path):
    service, _path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    session_id = service.create_session(course_id=course["id"], title="Concept help")
    view = service.session_view(session_id)
    assert view["course_id"] == course["id"]
    assert view["mode"] == "concept"
    assert view["source_policy"] == "source_only"
    assert view["status"] == "active"
    assert view["title"] == "Concept help"
    assert view["turns"] == []


def test_create_session_accepts_source_first_and_keeps_scope_immutable(tmp_path):
    service, _path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    session_id = service.create_session(
        course_id=course["id"],
        mode="exam",
        source_policy="source_first",
        title="Exam prep",
    )
    view = service.session_view(session_id)
    assert (view["course_id"], view["mode"], view["source_policy"]) == (
        course["id"], "exam", "source_first"
    )


def test_create_session_rejects_invalid_mode_policy_and_course(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebValidationError

    service, _path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(course_id=course["id"], mode="invalid")
    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(course_id=course["id"], source_policy="internet_only")
    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(course_id="missing-course")


def test_session_view_missing_session_is_safe_404_boundary(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebNotFoundError

    service, _path, _course, _provider, _retrieval = build_test_web_service(tmp_path)
    with pytest.raises(AcademicAgentWebNotFoundError, match="Tutor session was not found"):
        service.session_view("missing-session")


def test_ask_persists_grounded_exchange_and_only_tutor_tables_change(tmp_path):
    provider = FakeProvider(configured=True)
    base_path = copied_learning_database_path(tmp_path)
    connection = open_database(base_path)
    course = first_course(connection)
    hit = first_retrieval_hit(connection)
    before = table_counts(connection)
    connection.close()

    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService
    retrieval = FakeRetrieval((hit,))
    service = AcademicAgentWebService(
        database_path=base_path,
        index_root=tmp_path / "retrieval",
        course_catalogue_loader=deterministic_course_loader(course),
        provider_factory=lambda: provider,
        retrieval_service_factory=lambda _root: retrieval,
    )
    session_id = service.create_session(course_id=course["id"])
    view = service.ask(session_id, "Explain this concept from my project source.")

    assert provider.calls == 1
    assert [turn["role"] for turn in view["turns"]][-2:] == ["user", "assistant"]
    assert view["turns"][-1]["support_level"] == "grounded"
    assert view["turns"][-1]["evidence"][0]["citation_label"] == "S1"
    assert view["turns"][-1]["provider_model"] == "fake-model"

    connection = open_database(base_path)
    after = table_counts(connection)
    connection.close()
    changed = changed_tables(before, after)
    assert changed <= {"tutor_sessions", "tutor_turns", "tutor_evidence_links"}
    assert {"tutor_sessions", "tutor_turns", "tutor_evidence_links"} <= changed
    assert before["tutor_feedback"] == after["tutor_feedback"]


def test_ask_rejects_blank_question_without_turns(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebValidationError

    service, path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    session_id = service.create_session(course_id=course["id"])
    connection = open_database(path)
    before = connection.execute("SELECT COUNT(*) FROM tutor_turns").fetchone()[0]
    connection.close()
    with pytest.raises(AcademicAgentWebValidationError, match="Question cannot be empty"):
        service.ask(session_id, "   ")
    connection = open_database(path)
    after = connection.execute("SELECT COUNT(*) FROM tutor_turns").fetchone()[0]
    connection.close()
    assert before == after


def test_provider_unavailable_is_safe_and_does_not_persist_normal_turns(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService, AcademicAgentWebUnavailableError
    from personal_learning_assistant.tutor.provider import TutorProviderUnavailableError

    class UnavailableProvider:
        configured = False
        def complete(self, request):
            raise TutorProviderUnavailableError("SECRET-PROVIDER-DETAIL")

    path = copied_learning_database_path(tmp_path)
    connection = open_database(path)
    course = first_course(connection)
    hit = first_retrieval_hit(connection)
    connection.close()
    service = AcademicAgentWebService(
        database_path=path,
        course_catalogue_loader=deterministic_course_loader(course),
        provider_factory=lambda: UnavailableProvider(),
        retrieval_service_factory=lambda _root: FakeRetrieval((hit,)),
    )
    session_id = service.create_session(course_id=course["id"])
    with pytest.raises(AcademicAgentWebUnavailableError) as captured:
        service.ask(session_id, "Explain it")
    assert str(captured.value) == "AI tutor is not configured on this machine."
    assert service.session_view(session_id)["turns"] == []


def test_provider_request_failure_is_safe_and_does_not_persist_normal_turns(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService, AcademicAgentWebUnavailableError
    from personal_learning_assistant.tutor.http_provider import TutorProviderRequestError

    class FailingProvider:
        configured = True
        def complete(self, request):
            raise TutorProviderRequestError("SECRET-HTTP-DETAIL")

    path = copied_learning_database_path(tmp_path)
    connection = open_database(path)
    course = first_course(connection)
    hit = first_retrieval_hit(connection)
    connection.close()
    service = AcademicAgentWebService(
        database_path=path,
        course_catalogue_loader=deterministic_course_loader(course),
        provider_factory=lambda: FailingProvider(),
        retrieval_service_factory=lambda _root: FakeRetrieval((hit,)),
    )
    session_id = service.create_session(course_id=course["id"])
    with pytest.raises(AcademicAgentWebUnavailableError) as captured:
        service.ask(session_id, "Explain it")
    assert str(captured.value) == "The AI tutor could not complete this request. Your academic data was not changed."
    assert service.session_view(session_id)["turns"] == []


def test_insufficient_evidence_persists_bounded_response_without_provider_call(tmp_path):
    provider = FakeProvider(configured=True)
    service, _path, course, provider, _retrieval = build_test_web_service(tmp_path, provider=provider, hits=())
    session_id = service.create_session(course_id=course["id"])
    view = service.ask(session_id, "What does my project say about this missing topic?")
    assert provider.calls == 0
    assert view["turns"][-1]["role"] == "assistant"
    assert view["turns"][-1]["support_level"] == "insufficient"
    assert view["turns"][-1]["content"] == "I do not have enough project evidence to answer this question within the current tutor scope."
    assert view["turns"][-1]["evidence"] == []


class FakeWebService:
    def __init__(self):
        self.llm_calls = 0
        self.ask_calls = 0
        self.created = []
        self.session = {
            "session_id": "session-1",
            "course_id": "course-1",
            "topic_id": None,
            "assessment_id": None,
            "resource_id": None,
            "mode": "concept",
            "source_policy": "source_only",
            "status": "active",
            "title": "LU Doubts",
            "created_at": "2026-09-17T10:00:00Z",
            "updated_at": "2026-09-17T10:00:00Z",
            "completed_at": None,
            "turns": [],
        }

    def workspace(self, course_code=""):
        return {
            "available": True,
            "message": "",
            "provider_configured": True,
            "courses": [{"id": "course-1", "code": "MA103N", "name": "Linear Algebra"}],
            "selected_course_code": course_code,
            "mentor": None,
            "sessions": [dict(self.session)],
            "modes": ["concept", "doubt", "summary", "exam", "lecture", "revision", "guidance", "free"],
            "source_policies": ["source_only", "source_first"],
        }

    def create_session(self, **kwargs):
        self.created.append(kwargs)
        return "session-1"

    def session_view(self, session_id):
        if session_id != "session-1":
            from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebNotFoundError
            raise AcademicAgentWebNotFoundError("Tutor session was not found.")
        return dict(self.session)

    def ask(self, session_id, question):
        self.ask_calls += 1
        self.llm_calls += 1
        return dict(self.session)


def fake_web_app(fake_service):
    from personal_learning_assistant.ui.web import create_app

    return create_app({
        "TESTING": True,
        "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: fake_service,
    })


def test_agent_routes_are_get_safe_and_ask_is_explicit_post():
    fake = FakeWebService()
    client = fake_web_app(fake).test_client()
    assert client.get("/agent").status_code == 200
    assert fake.llm_calls == 0
    assert client.get("/agent?course=MA103N").status_code == 200
    assert fake.llm_calls == 0
    created = client.post("/agent/sessions", data={
        "course_id": "course-1",
        "mode": "concept",
        "source_policy": "source_only",
        "title": "LU Doubts",
    })
    assert created.status_code == 303
    assert created.headers["Location"].endswith("/agent/sessions/session-1")
    assert fake.llm_calls == 0
    assert client.get("/agent/sessions/session-1").status_code == 200
    assert fake.llm_calls == 0
    asked = client.post("/agent/sessions/session-1/ask", data={"question": "Why does elimination produce L and U?", "mode": "exam", "source_policy": "source_first"})
    assert asked.status_code == 303
    assert fake.ask_calls == 1
    assert fake.llm_calls == 1
    assert client.post("/agent").status_code == 405
    assert client.post("/agent/execute").status_code == 404


def test_agent_page_renders_provider_mentor_and_session_controls_without_execution_controls():
    fake = FakeWebService()
    response = fake_web_app(fake).test_client().get("/agent")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in ("Academic Agent", "Configured", "Choose a course for advice", "Start a tutor session", "Recent tutor sessions", "Source Only"):
        assert expected in text
    assert 'method="post"' in text.lower()
    assert 'action="/agent/sessions"' in text
    assert "/agent/execute" not in text


def test_agent_session_page_renders_transcript_support_provider_and_evidence():
    fake = FakeWebService()
    fake.session["turns"] = [
        {"turn_id": "u1", "ordinal": 1, "role": "user", "content": "Explain LU", "support_level": "not_evaluated", "provider_name": "", "provider_model": "", "created_at": "2026-09-17T10:01:00Z", "evidence": []},
        {"turn_id": "a1", "ordinal": 2, "role": "assistant", "content": "Grounded answer [S1]", "support_level": "grounded", "provider_name": "fake-provider", "provider_model": "fake-model", "created_at": "2026-09-17T10:02:00Z", "evidence": [{"citation_label": "S1", "chunk_id": "chunk-1", "document_id": "doc-1", "relation_type": "support", "retrieval_score": 0.9}]},
    ]
    response = fake_web_app(fake).test_client().get("/agent/sessions/session-1")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in ("Explain LU", "Grounded answer [S1]", "Support: Grounded", "fake-provider · fake-model", "S1 · document doc-1 · chunk chunk-1", "Ask grounded tutor"):
        assert expected in text


def test_ask_route_ignores_posted_scope_fields():
    fake = FakeWebService()
    client = fake_web_app(fake).test_client()
    original = (fake.session["course_id"], fake.session["mode"], fake.session["source_policy"])
    response = client.post(
        "/agent/sessions/session-1/ask",
        data={
            "question": "Explain rank",
            "course_id": "other-course",
            "mode": "exam",
            "source_policy": "source_first",
        },
    )
    assert response.status_code == 303
    assert (fake.session["course_id"], fake.session["mode"], fake.session["source_policy"]) == original


def test_base_navigation_exposes_academic_agent_as_real_link():
    source = (ROOT / "personal_learning_assistant/ui/web/templates/base.html").read_text(encoding="utf-8")
    assert "url_for('web.academic_agent')" in source
    assert "active_page == 'agent'" in source
    assert '<span class="nav-item is-disabled" aria-disabled="true">Academic Agent</span>' not in source


def test_web_production_code_has_no_phase68_execution_path():
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "personal_learning_assistant/services/academic_agent_web_service.py",
            "personal_learning_assistant/ui/web/routes.py",
            "personal_learning_assistant/ui/web/templates/agent.html",
            "personal_learning_assistant/ui/web/templates/agent_session.html",
        )
    )
    forbidden = (
        "AcademicAgentService",
        ".execute(",
        "EXECUTE_ACADEMIC_AGENT_ACTION",
        "practice_quiz",
        "lecture_learning",
        "/execute",
    )
    for token in forbidden:
        assert token not in sources


def test_web_app_creation_keeps_agent_provider_retrieval_and_mentor_lazy(tmp_path):
    script = r'''
import sys
from personal_learning_assistant.ui.web import create_app
create_app({"TESTING": True})
for name in (
    "personal_learning_assistant.services.grounded_tutor_service",
    "personal_learning_assistant.services.adaptive_mentor_service",
    "personal_learning_assistant.retrieval.index_store",
    "personal_learning_assistant.tutor.http_provider",
):
    assert name not in sys.modules, name
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_real_agent_get_does_not_change_production_database_or_retrieval_index():
    from personal_learning_assistant.ui.web import create_app

    database = ROOT / "data" / "learning_assistant.db"
    retrieval = ROOT / ".phase5_retrieval"
    assert database.is_file()
    db_before = file_hash(database)
    index_before = tree_hashes(retrieval)
    response = create_app({"TESTING": True}).test_client().get("/agent")
    assert response.status_code == 200
    assert file_hash(database) == db_before
    assert tree_hashes(retrieval) == index_before


def test_real_session_get_is_read_only_when_a_session_exists():
    from personal_learning_assistant.ui.web import create_app

    database = ROOT / "data" / "learning_assistant.db"
    connection = sqlite3.connect("file:{}?mode=ro".format(str(database.resolve()).replace("\\", "/")), uri=True)
    row = connection.execute("SELECT id FROM tutor_sessions ORDER BY updated_at DESC,id DESC LIMIT 1").fetchone()
    connection.close()
    if row is None:
        pytest.skip("production database has no tutor session to reopen")
    before = file_hash(database)
    response = create_app({"TESTING": True}).test_client().get("/agent/sessions/{}".format(row[0]))
    assert response.status_code == 200
    assert file_hash(database) == before


def test_create_session_persists_explicit_topic_scope(tmp_path):
    service, database_path, course, _provider, _retrieval = build_test_web_service(tmp_path)
    connection = open_database(database_path)
    try:
        row = connection.execute(
            "SELECT id,name FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL "
            "ORDER BY position,name,id LIMIT 1",
            (course["id"],),
        ).fetchone()
        assert row is not None, "Tutor topic-scope test requires one course topic"
        topic_id = str(row[0])
    finally:
        connection.close()

    session_id = service.create_session(
        course_id=course["id"],
        topic_id=topic_id,
        mode="doubt",
        source_policy="source_first",
        title="LU Factorization",
    )
    view = service.session_view(session_id)

    assert view["course_id"] == course["id"]
    assert view["topic_id"] == topic_id
    assert view["mode"] == "doubt"
    assert view["source_policy"] == "source_first"


def test_create_session_rejects_missing_or_cross_course_topic_scope(tmp_path):
    service, database_path, course, _provider, _retrieval = build_test_web_service(tmp_path)

    from personal_learning_assistant.services.academic_agent_web_service import (
        AcademicAgentWebValidationError,
    )

    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(
            course_id=course["id"],
            topic_id="missing-topic",
        )

    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(
            course_id="",
            topic_id="missing-topic",
        )


def test_agent_create_session_route_forwards_topic_id():
    fake = FakeWebService()
    client = fake_web_app(fake).test_client()

    response = client.post(
        "/agent/sessions",
        data={
            "course_id": "course-1",
            "topic_id": "topic-lu",
            "mode": "doubt",
            "source_policy": "source_first",
            "title": "LU Factorization",
        },
    )

    assert response.status_code == 303
    assert fake.created[-1]["topic_id"] == "topic-lu"


def test_agent_page_exposes_explicit_topic_scope_control():
    fake = FakeWebService()
    response = fake_web_app(fake).test_client().get("/agent")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="session-topic"' in text
    assert 'name="topic_id"' in text
    assert "Topic scope" in text
