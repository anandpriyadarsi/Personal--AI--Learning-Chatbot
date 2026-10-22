"""Normal Tutor creation must preserve the student's canonical topic scope."""
import pytest

from tests.test_phase7_5_academic_agent_web import build_test_web_service, open_database, table_counts
from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebValidationError


def test_workspace_exposes_canonical_topics_without_writes(tmp_path):
    service, path, course, provider, _ = build_test_web_service(tmp_path)
    connection = open_database(path)
    before = table_counts(connection)
    connection.close()
    workspace = service.workspace()
    assert workspace["tutor_topics"] == [{"id": "synthetic-rank", "course_id": course["id"],
                                          "name": "Matrix Rank"}]
    connection = open_database(path)
    assert table_counts(connection) == before
    connection.close()
    assert provider.calls == 0


def test_session_creation_preserves_topic_id(tmp_path):
    service, path, course, _, _ = build_test_web_service(tmp_path)
    session_id = service.create_session(course_id=course["id"], topic_id="synthetic-rank")
    assert service.session_view(session_id)["topic_id"] == "synthetic-rank"
    assert service.session_view(session_id)["topic"]["name"] == "Matrix Rank"


@pytest.mark.parametrize("course_id,topic_id", [
    ("", "synthetic-rank"), ("synthetic-ma", "unknown-topic"), ("other-course", "synthetic-rank"),
])
def test_forged_or_course_less_topic_is_rejected_without_creating_session(tmp_path, course_id, topic_id):
    service, path, _, _, _ = build_test_web_service(tmp_path)
    connection = open_database(path)
    connection.execute("INSERT INTO courses(id,code,name,status,created_at,updated_at) "
                       "VALUES('other-course','UC100N','Data Science','active','2026-10-22','2026-10-22')")
    before = table_counts(connection)
    connection.close()
    with pytest.raises(AcademicAgentWebValidationError):
        service.create_session(course_id=course_id, topic_id=topic_id)
    connection = open_database(path)
    assert table_counts(connection) == before
    connection.close()
