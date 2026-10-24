"""Android Assessment Studio catalogue bridge regression tests.

Synthetic data only; never depend on the owner's private academic database.
"""
from contextlib import closing
import sqlite3

from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.android_assessment_catalogue import (
    synchronize_android_assessment_courses,
)


def state(*, name="Indian Knowledge System", topics=None):
    return {"courses": [
        {"id": "learn-uc103n", "code": "UC103N", "name": name,
         "topics": topics if topics is not None else [
             {"name": "Nyaya"}, {"name": "Advaita Vedanta"}
         ]},
        {"id": "learn-extra", "code": "FAKE01", "name": "Not a confirmed Semester 1 subject",
         "topics": [{"name": "Should not import"}]},
    ]}


def db_at(tmp_path):
    path = tmp_path / "assessment.sqlite3"
    apply_migrations(path, enable_extended_assessment=True)
    return path


def test_missing_uc103n_is_added_to_sqlite_and_repeated_sync_is_idempotent(tmp_path):
    db = db_at(tmp_path)
    backups = tmp_path / "backups"
    result = synchronize_android_assessment_courses(
        db, course_state=state(), backup_path=backups,
    )
    assert result == {"courses_added": 1, "topics_added": 2}
    with closing(sqlite3.connect(db)) as connection:
        courses = connection.execute(
            "SELECT id,code,name FROM courses"
        ).fetchall()
        assert courses == [("android-course-uc103n", "UC103N", "Indian Knowledge System")]
        rows = connection.execute(
            "SELECT name,status FROM topics ORDER BY position"
        ).fetchall()
        assert rows == [("Nyaya", "not_started"), ("Advaita Vedanta", "not_started")]
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert len(list(backups.glob("assessment-before-0015-*.sqlite3"))) == 1
    assert synchronize_android_assessment_courses(
        db, course_state=state(), backup_path=backups
    ) == {"courses_added": 0, "topics_added": 0}
    assert len(list(backups.glob("assessment-before-0015-*.sqlite3"))) == 1


def test_existing_sqlite_course_identity_and_topic_progress_are_untouched(tmp_path):
    db = db_at(tmp_path)
    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            "INSERT INTO courses (id,code,name,created_at,updated_at) "
            "VALUES ('owned-course','UC103N','Original IKS','t','t')"
        )
        connection.execute(
            "INSERT INTO topics "
            "(id,course_id,name,normalized_name,status,confidence,created_at,updated_at) "
            "VALUES ('owned-topic','owned-course','Nyaya','nyaya','mastered',5,'t','t')"
        )
        connection.commit()
    result = synchronize_android_assessment_courses(
        db, course_state=state(name="Different Learn Label"), backup_path=tmp_path / "backups"
    )
    assert result == {"courses_added": 0, "topics_added": 1}
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute(
            "SELECT id,name FROM courses WHERE code='UC103N'"
        ).fetchone() == ("owned-course", "Original IKS")
        assert connection.execute(
            "SELECT id,status,confidence FROM topics WHERE normalized_name='nyaya'"
        ).fetchone() == ("owned-topic", "mastered", 5)
        assert connection.execute(
            "SELECT course_id FROM topics WHERE normalized_name='advaita vedanta'"
        ).fetchone() == ("owned-course",)


def test_deleted_course_is_not_resurrected(tmp_path):
    db = db_at(tmp_path)
    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            "INSERT INTO courses (id,code,name,created_at,updated_at,deleted_at) "
            "VALUES ('deleted-course','UC103N','Original IKS','t','t','t')"
        )
        connection.commit()
    assert synchronize_android_assessment_courses(
        db, course_state=state(), backup_path=tmp_path / "backups"
    ) == {"courses_added": 0, "topics_added": 0}
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute(
            "SELECT deleted_at FROM courses WHERE id='deleted-course'"
        ).fetchone() == ("t",)


def test_no_learn_subject_does_not_create_fictitious_sqlite_subject(tmp_path):
    db = db_at(tmp_path)
    assert synchronize_android_assessment_courses(
        db, course_state={"courses": []}, backup_path=tmp_path / "backups"
    ) == {"courses_added": 0, "topics_added": 0}
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM courses").fetchone() == (0,)
