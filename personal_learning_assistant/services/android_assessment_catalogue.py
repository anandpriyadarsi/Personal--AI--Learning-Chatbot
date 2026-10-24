"""Additive Android bridge for the existing Learn -> Assessment subject catalogue.

Learn retains its authoritative course records. Assessment Studio has a distinct
SQLite authoring catalogue; a fresh phone DB can otherwise contain zero courses.
Only the confirmed Semester 1 codes already present in Learn are projected.
Do not overwrite existing rows, course/topic identities or progress.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from personal_learning_assistant.services.android_subject_restore import SEMESTER_ONE_CODES


def _normal(value):
    return " ".join(str(value or "").split()).casefold()


def synchronize_android_assessment_courses(
    database_path, *, course_state=None, backup_path=None,
):
    """Add missing approved subject/topic rows to the Android assessment store.

    Existing SQLite course IDs and topic IDs are never updated or deleted.
    SQLite is backed up before a write. No grades, learning events, question
    attempts or inferred mastery are imported from the Learn presentation.
    Caller is the trusted phone-local launcher, after all migrations are applied.
    """
    if course_state is None:
        from personal_learning_assistant.repositories.routed_course_repository import (
            RoutedCourseRepository,
        )
        course_state = RoutedCourseRepository().load_state()
    if not isinstance(course_state, dict) or not isinstance(course_state.get("courses"), list):
        raise ValueError("Existing Learn course catalogue is unavailable; no sync performed.")
    by_code = {}
    for item in course_state["courses"]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().upper()
        if code in SEMESTER_ONE_CODES and code not in by_code:
            by_code[code] = item

    path = Path(database_path)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Existing assessment SQLite database is unavailable.")
    if backup_path is None:
        from config import BACKUP_PATH
        backup_path = BACKUP_PATH

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Assessment SQLite integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Assessment SQLite foreign-key check failed.")
        stored = {
            str(code).strip().upper(): (row_id, deleted_at)
            for row_id, code, deleted_at in db.execute(
                "SELECT id, code, deleted_at FROM courses"
            )
        }
        pending_courses = []
        pending_topics = []
        for code in SEMESTER_ONE_CODES:
            item = by_code.get(code)
            if item is None:
                continue  # Never invent a course absent from the real Learn state.
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValueError("Existing Learn course has no name: " + code)
            existing = stored.get(code)
            if existing and existing[1]:
                continue  # Respect intentional archived/deleted SQLite records.
            course_id = existing[0] if existing else "android-course-" + code.lower()
            if existing is None:
                pending_courses.append((course_id, code, name, timestamp, timestamp))
            present = {
                row[0] for row in db.execute(
                    "SELECT normalized_name FROM topics WHERE course_id=?",
                    (course_id,),
                )
            } if existing else set()
            raw_topics = item.get("topics") or ()
            if not isinstance(raw_topics, (list, tuple)):
                raise ValueError("Existing Learn course topics have an invalid shape.")
            seen = set(present)
            for position, topic in enumerate(raw_topics):
                if not isinstance(topic, dict):
                    continue
                topic_name = str(topic.get("name") or "").strip()
                normalized = _normal(topic_name)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                topic_id = "android-topic-" + code.lower() + "-" + __import__("hashlib").sha256(
                    normalized.encode("utf-8")
                ).hexdigest()[:24]
                pending_topics.append(
                    (topic_id, course_id, topic_name, normalized, position, timestamp, timestamp)
                )

        if not pending_courses and not pending_topics:
            return {"courses_added": 0, "topics_added": 0}

        # First write on an existing phone store is backup-first. Keep this
        # outside the transaction because SQLite's backup API uses a second
        # read-only connection.
        from personal_learning_assistant.services.assessment_activation import _make_backup
        _make_backup(path, Path(backup_path))
        try:
            db.execute("BEGIN IMMEDIATE")
            for row in pending_courses:
                db.execute(
                    "INSERT INTO courses (id, code, name, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)", row
                )
            for row in pending_topics:
                db.execute(
                    "INSERT INTO topics "
                    "(id, course_id, name, normalized_name, position, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", row
                )
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Assessment subject sync failed foreign-key verification.")
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"courses_added": len(pending_courses), "topics_added": len(pending_topics)}
