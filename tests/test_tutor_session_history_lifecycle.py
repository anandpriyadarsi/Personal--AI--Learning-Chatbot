"""Regression: contextual tutor titles and pruning only genuinely empty sessions."""
from datetime import datetime, timedelta, timezone

from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
from personal_learning_assistant.services.tutor_session_service import (
    TutorSessionService,
    suggest_tutor_session_title,
)
from tests.test_phase7_5_academic_agent_web import build_test_web_service, open_database


def _user_turn(path, session_id, question):
    connection = open_database(path)
    try:
        return TutorSessionService(SQLiteTutorRepository(connection)).add_user_turn(
            session_id, question
        )
    finally:
        connection.close()


def test_short_conversational_titles_need_no_provider_and_keep_acronyms():
    assert suggest_tutor_session_title("Hi") == ""
    assert suggest_tutor_session_title("Hello, Alex!") == ""
    assert suggest_tutor_session_title(
        "Alex, can you please explain LU factorization step by step?"
    ) == "Explain LU factorization step by step"
    assert suggest_tutor_session_title(
        "Can you generate 10 MCQs from my lead-acid battery PDF?"
    ) == "Generate 10 MCQs from my lead-acid battery PDF"
    assert len(suggest_tutor_session_title("Explain " + "eigenvalues " * 50)) <= 80
    assert "`" not in suggest_tutor_session_title("Explain ```secret``` LU factorization")


def test_first_meaningful_user_turn_sets_title_but_never_overrides_manual_name(tmp_path):
    service, path, course, provider, _ = build_test_web_service(tmp_path)
    automatic = service.create_session(course_id=course["id"])
    assert service.session_view(automatic)["title"] == ""
    _user_turn(path, automatic, "Hi")
    assert service.session_view(automatic)["title"] == ""
    _user_turn(path, automatic, "Please explain Gaussian elimination with an example.")
    assert service.session_view(automatic)["title"] == "Explain Gaussian elimination with an example"
    manual = service.create_session(course_id=course["id"], title="My Linear Algebra practice")
    _user_turn(path, manual, "Explain eigenvectors and eigenvalues using a matrix.")
    assert service.session_view(manual)["title"] == "My Linear Algebra practice"
    service.rename_session(automatic, "Custom title")
    _user_turn(path, automatic, "What is an LU decomposition?")
    assert service.session_view(automatic)["title"] == "Custom title"
    assert provider.calls == 0


def test_history_excludes_empty_shells_and_derives_legacy_names_read_only(tmp_path):
    service, path, course, provider, _ = build_test_web_service(tmp_path)
    untouched = service.create_session(course_id=course["id"], title="Unused draft")
    populated = service.create_session(course_id=course["id"])
    _user_turn(path, populated, "How does Gaussian elimination find matrix rank?")
    connection = open_database(path)
    try:
        connection.execute("UPDATE tutor_sessions SET title='' WHERE id=?", (populated,))
    finally:
        connection.close()
    view = service.workspace()
    assert untouched not in [item["session_id"] for item in view["sessions"]]
    assert next(item for item in view["sessions"] if item["session_id"] == populated)["title"] == (
        "How does Gaussian elimination find matrix rank"
    )
    # Projection does not write the derived label into stored sessions on GET.
    assert service.session_view(populated)["title"] == ""
    assert provider.calls == 0


def test_prunes_only_stale_empty_shells_during_explicit_write(tmp_path):
    service, path, course, provider, _ = build_test_web_service(tmp_path)
    old_empty = service.create_session(course_id=course["id"])
    old_populated = service.create_session(course_id=course["id"])
    _user_turn(path, old_populated, "Explain Gaussian elimination with examples.")
    old_stamp = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    connection = open_database(path)
    try:
        connection.execute(
            "UPDATE tutor_sessions SET created_at=?,updated_at=? WHERE id IN (?,?)",
            (old_stamp, old_stamp, old_empty, old_populated),
        )
    finally:
        connection.close()

    new_empty = service.create_session(course_id=course["id"])
    connection = open_database(path)
    try:
        remaining = {
            str(row[0]) for row in connection.execute("SELECT id FROM tutor_sessions")
        }
    finally:
        connection.close()
    assert old_empty not in remaining
    assert old_populated in remaining
    assert new_empty in remaining
    assert provider.calls == 0
