"""SQLite ledger for the read-only Moodle connector."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class MoodleSyncRepositoryError(RuntimeError):
    pass


def _open(path, *, writable):
    database = Path(path)
    if not database.is_file() or database.is_symlink():
        raise MoodleSyncRepositoryError("Academic database is unavailable.")
    uri = "file:{}?mode={}".format(
        quote(str(database.resolve(strict=False)).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )
    try:
        connection = sqlite3.connect(
            uri,
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "moodle_sync_files" not in tables:
            connection.close()
            raise MoodleSyncRepositoryError(
                "Moodle connector migration 0008 is not applied."
            )
        return connection
    except MoodleSyncRepositoryError:
        raise
    except sqlite3.Error as error:
        raise MoodleSyncRepositoryError("Moodle sync storage is unavailable.") from error


class SQLiteMoodleSyncRepository:
    def __init__(self, database_path="data/learning_assistant.db"):
        self.database_path = Path(database_path)

    def courses(self):
        c = _open(self.database_path, writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT id,code,name FROM courses "
                    "WHERE deleted_at IS NULL ORDER BY code,id"
                ).fetchall()
            )
        finally:
            c.close()

    def find_file(self, moodle_course_id, module_id, file_url):
        c = _open(self.database_path, writable=False)
        try:
            row = c.execute(
                "SELECT * FROM moodle_sync_files "
                "WHERE moodle_course_id=? AND module_id=? AND file_url=?",
                (str(moodle_course_id), str(module_id), str(file_url)),
            ).fetchone()
            return None if row is None else dict(row)
        finally:
            c.close()

    def list_files(self, *, limit=100):
        c = _open(self.database_path, writable=False)
        try:
            return tuple(
                dict(row)
                for row in c.execute(
                    "SELECT * FROM moodle_sync_files "
                    "ORDER BY last_seen_at DESC,course_shortname,module_name,file_name "
                    "LIMIT ?",
                    (int(limit),),
                ).fetchall()
            )
        finally:
            c.close()

    def upsert_seen(self, row):
        c = _open(self.database_path, writable=True)
        try:
            with transaction(c, immediate=True):
                c.execute(
                    "INSERT INTO moodle_sync_files "
                    "(id,moodle_course_id,anvaya_course_id,course_shortname,course_name,"
                    "module_id,module_name,file_name,file_url,mime_type,"
                    "external_content_hash,external_modified_at,local_path,status,"
                    "first_seen_at,last_seen_at,downloaded_at,error) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'seen',?,?,NULL,'') "
                    "ON CONFLICT(moodle_course_id,module_id,file_url) DO UPDATE SET "
                    "anvaya_course_id=excluded.anvaya_course_id,"
                    "course_shortname=excluded.course_shortname,"
                    "course_name=excluded.course_name,module_name=excluded.module_name,"
                    "file_name=excluded.file_name,mime_type=excluded.mime_type,"
                    "external_content_hash=excluded.external_content_hash,"
                    "external_modified_at=excluded.external_modified_at,"
                    "last_seen_at=excluded.last_seen_at,error=''",
                    (
                        row["id"], row["moodle_course_id"], row.get("anvaya_course_id"),
                        row.get("course_shortname", ""), row.get("course_name", ""),
                        row.get("module_id", ""), row.get("module_name", ""),
                        row["file_name"], row["file_url"], row.get("mime_type", ""),
                        row.get("external_content_hash", ""),
                        row.get("external_modified_at", ""), row.get("local_path"),
                        row["first_seen_at"], row["last_seen_at"],
                    ),
                )
        finally:
            c.close()
        return self.find_file(
            row["moodle_course_id"], row.get("module_id", ""), row["file_url"]
        )

    def mark_downloaded(self, moodle_course_id, module_id, file_url, *, local_path, downloaded_at):
        c = _open(self.database_path, writable=True)
        try:
            with transaction(c, immediate=True):
                cur = c.execute(
                    "UPDATE moodle_sync_files SET status='downloaded',local_path=?,"
                    "downloaded_at=?,error='' "
                    "WHERE moodle_course_id=? AND module_id=? AND file_url=?",
                    (
                        str(local_path), downloaded_at, str(moodle_course_id),
                        str(module_id), str(file_url),
                    ),
                )
                if cur.rowcount != 1:
                    raise MoodleSyncRepositoryError("Moodle ledger row disappeared.")
        finally:
            c.close()

    def mark_failed(self, moodle_course_id, module_id, file_url, *, error_text):
        c = _open(self.database_path, writable=True)
        try:
            with transaction(c, immediate=True):
                c.execute(
                    "UPDATE moodle_sync_files SET status='failed',error=? "
                    "WHERE moodle_course_id=? AND module_id=? AND file_url=?",
                    (
                        " ".join(str(error_text or "download failed").split())[:500],
                        str(moodle_course_id), str(module_id), str(file_url),
                    ),
                )
        finally:
            c.close()
