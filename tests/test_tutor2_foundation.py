from __future__ import annotations

import sqlite3

from personal_learning_assistant.domain.tutor_models import (
    TutorProviderResponse,
    TutorSessionSpec,
)
from personal_learning_assistant.repositories.sqlite.migration_runner import (
    apply_migrations,
)
from personal_learning_assistant.repositories.sqlite.tutor_repository import (
    SQLiteTutorRepository,
)
from personal_learning_assistant.services.grounded_tutor_service import (
    GroundedTutorService,
)
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
)
from personal_learning_assistant.ui.web.tutor_rendering import (
    render_tutor_markdown,
)


class EmptyRetrieval:
    def search(self, *args, **kwargs):
        return ()


class GeneralProvider:
    configured = True

    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return TutorProviderResponse(
            content=(
                "General explanation (not from project sources)\n\n"
                "Think of a basis as a spanning set with no redundant vectors."
            ),
            provider_name="fake-provider",
            provider_model="fake-model",
            request_id="req-general",
        )


def test_tutor_markdown_renders_readable_safe_html():
    html = str(
        render_tutor_markdown(
            "### What is **Span**?\n\n"
            "$v_1 = \\begin{pmatrix}1\\\\0\\end{pmatrix}$ [S1]\n\n"
            "<script>alert('x')</script>"
        )
    )
    assert "<h3>What is <strong>Span</strong>?</h3>" in html
    assert "pmatrix" in html
    assert 'href="#source-S1"' in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_source_first_can_teach_when_project_retrieval_is_empty(tmp_path):
    path = tmp_path / "tutor2.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = sessions.create_session(
        TutorSessionSpec(
            mode="concept",
            source_policy="source_first",
            title="Basis doubts",
        )
    )
    provider = GeneralProvider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=EmptyRetrieval(),
        provider=provider,
    )

    result = engine.answer(
        session.session_id,
        "I understand span but why does a basis need linear independence?",
    )

    assert len(provider.requests) == 1
    assert result.assistant_turn.support_level == "mixed"
    assert result.assistant_turn.evidence == ()
    assert result.citations == ()
    assert "no redundant vectors" in result.assistant_turn.content
    assert [turn.role for turn in sessions.transcript(session.session_id)] == [
        "user",
        "assistant",
    ]
    connection.close()


def test_tutor2_system_prompt_is_pedagogical_not_search_like():
    from personal_learning_assistant.tutor.grounding import _system_prompt

    prompt = _system_prompt(
        mode="doubt",
        source_policy="source_first",
        purpose="Diagnose a specific confusion without skipping prerequisites.",
        preferred_source_roles=("professor", "course", "personal_note"),
    )
    assert "personal academic tutor, not a search-results page" in prompt
    assert "student understanding" in prompt
    assert "hint only" in prompt
    assert "missing idea or misconception" in prompt
    assert "intuition -> example -> formal detail" in prompt
    assert "General explanation (not from project sources)" in prompt


def test_web_new_tutor_defaults_to_source_first():
    from personal_learning_assistant.ui.web import create_app

    calls = []

    class FakeService:
        def create_session(self, **payload):
            calls.append(payload)
            return "session-2"

    app = create_app(
        {
            "TESTING": True,
            "ACADEMIC_AGENT_WEB_SERVICE_FACTORY": lambda: FakeService(),
        }
    )
    response = app.test_client().post(
        "/agent/sessions",
        data={
            "course_id": "",
            "mode": "concept",
            "title": "Tutor 2",
        },
    )
    assert response.status_code == 303
    assert calls[0]["source_policy"] == "source_first"


def test_session_view_uses_human_course_label(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import (
        AcademicAgentWebService,
    )

    path = tmp_path / "course-label.db"
    apply_migrations(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO courses "
        "(id,code,name,status,description,created_at,updated_at,deleted_at) "
        "VALUES ('course-1','MA103N','Linear Algebra','active','','x','x',NULL)"
    )
    connection.commit()
    connection.close()

    service = AcademicAgentWebService(
        database_path=path,
        course_catalogue_loader=lambda: {
            "available": True,
            "courses": [
                {
                    "id": "course-1",
                    "code": "MA103N",
                    "name": "Linear Algebra",
                    "topics": [],
                }
            ],
        },
    )
    session_id = service.create_session(
        course_id="course-1",
        mode="concept",
        source_policy="source_first",
        title="Linear Algebra",
    )
    view = service.session_view(session_id)

    assert view["course_label"] == "MA103N · Linear Algebra"
    assert "course-1" not in view["course_label"]



def test_tutor_intent_router_respects_hint_quiz_and_verification_requests():
    from personal_learning_assistant.tutor.intent import classify_tutor_intent

    assert classify_tutor_intent(
        "Give me a hint only, do not solve it."
    ).name == "hint"
    assert classify_tutor_intent(
        "Quiz me one question at a time."
    ).name == "quiz"
    assert classify_tutor_intent(
        "Check my reasoning: is this correct?"
    ).name == "verify_reasoning"


def test_provider_request_carries_teaching_intent(tmp_path):
    path = tmp_path / "intent.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = sessions.create_session(
        TutorSessionSpec(
            mode="doubt",
            source_policy="source_first",
            title="Hint session",
        )
    )

    provider = GeneralProvider()
    engine = GroundedTutorService(
        tutor_session_service=sessions,
        retrieval_service=EmptyRetrieval(),
        provider=provider,
    )
    engine.answer(session.session_id, "Give me a hint only, do not solve it.")

    request = provider.requests[0]
    assert request.metadata["teaching_intent"] == "hint"
    assert "TEACHING INTENT" in request.messages[-1]["content"]
    assert "Do not reveal the full solution" in request.messages[-1]["content"]
    connection.close()


def test_tutor_feedback_is_explicit_and_stays_in_feedback_table(tmp_path):
    from personal_learning_assistant.services.academic_agent_web_service import (
        AcademicAgentWebService,
    )

    path = tmp_path / "feedback.db"
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    repository = SQLiteTutorRepository(connection)
    sessions = TutorSessionService(repository)
    session = sessions.create_session(
        TutorSessionSpec(
            mode="concept",
            source_policy="source_first",
            title="Feedback session",
        )
    )
    turn = sessions.add_assistant_turn(
        session.session_id,
        "A general teaching answer.",
        support_level="mixed",
        provider_name="fake",
        provider_model="fake-model",
    )
    connection.close()

    service = AcademicAgentWebService(
        database_path=path,
        course_catalogue_loader=lambda: {"available": True, "courses": []},
    )
    service.record_feedback(
        session.session_id,
        turn.turn_id,
        helpful=True,
    )

    connection = sqlite3.connect(path)
    assert connection.execute(
        "SELECT COUNT(*) FROM tutor_feedback"
    ).fetchone()[0] == 1
    assert connection.execute(
        "SELECT helpful FROM tutor_feedback"
    ).fetchone()[0] == 1
    connection.close()
