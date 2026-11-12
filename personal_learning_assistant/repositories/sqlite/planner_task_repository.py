"""SQLite task persistence for the Phase 7.5.13 Operational Planner."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.repositories.sqlite.connection import transaction


class PlannerTaskRepositoryError(RuntimeError):
    """Task persistence is unavailable or inconsistent."""


class PlannerTaskRepositoryConflictError(PlannerTaskRepositoryError):
    """An explicit manual intent conflicts with its canonical source or receipt."""


class PlannerTaskRepositoryNotFoundError(PlannerTaskRepositoryError):
    """The requested planner task does not exist."""


def _open(path: Path, *, writable: bool) -> sqlite3.Connection:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PlannerTaskRepositoryError("Operational planner storage is unavailable.")
    uri = quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:")
    try:
        c = sqlite3.connect(
            "file:{}?mode={}".format(uri, "rw" if writable else "ro"),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA busy_timeout = 5000")
        return c
    except sqlite3.Error as error:
        raise PlannerTaskRepositoryError("Operational planner storage is unavailable.") from error


class SQLitePlannerTaskRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self, *, writable: bool):
        c = _open(self.database_path, writable=writable)
        tables = {str(r[0]) for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "planner_tasks" not in tables:
            c.close()
            raise PlannerTaskRepositoryError("Operational planner migration is not applied.")
        return c

    def list_tasks(
        self,
        *,
        statuses=None,
        priority=None,
        course_id=None,
        due_from=None,
        due_to=None,
    ):
        sql = "SELECT * FROM planner_tasks WHERE 1=1"
        params = []
        if statuses:
            values = tuple(statuses)
            sql += " AND status IN ({})".format(",".join("?" for _ in values))
            params.extend(values)
        if priority:
            sql += " AND priority=?"
            params.append(priority)
        if course_id:
            sql += " AND course_id=?"
            params.append(course_id)
        if due_from:
            sql += " AND due_on>=?"
            params.append(due_from)
        if due_to:
            sql += " AND due_on<=?"
            params.append(due_to)
        sql += (
            " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,"
            " COALESCE(due_on,'9999-12-31'), created_at, id"
        )
        c = self._connect(writable=False)
        try:
            tasks = tuple(dict(r) for r in c.execute(sql, tuple(params)).fetchall())
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_work_logs'").fetchone():
                for task in tasks:
                    logs = tuple(dict(r) for r in c.execute(
                        'SELECT l.*,EXISTS(SELECT 1 FROM planner_work_logs n WHERE n.supersedes_id=l.id) AS superseded FROM planner_work_logs l WHERE task_id=? ORDER BY occurred_at,id', (task['id'],)))
                    for log in logs:
                        log['superseded'] = bool(log['superseded'])
                    task['work_logs'] = logs
                    task['recorded_minutes'] = sum(row['actual_minutes'] for row in logs if not row['superseded']) if logs else None
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_task_sources'").fetchone():
                for task in tasks:
                    task['sources'] = tuple(dict(r) for r in c.execute('SELECT * FROM planner_task_sources WHERE task_id=?', (task['id'],)))
            return tasks
        finally:
            c.close()

    def get_task(self, task_id):
        c = self._connect(writable=False)
        try:
            row = c.execute("SELECT * FROM planner_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise PlannerTaskRepositoryNotFoundError("Planner task was not found.")
            return dict(row)
        finally:
            c.close()

    def get_task_by_external_id(self, external_id):
        c = self._connect(writable=False)
        try:
            row = c.execute(
                "SELECT * FROM planner_tasks WHERE external_id=? "
                "ORDER BY created_at, id LIMIT 1",
                (str(external_id),),
            ).fetchone()
            if row is None:
                raise PlannerTaskRepositoryNotFoundError("Planner task was not found.")
            return dict(row)
        finally:
            c.close()

    def capture_catalogue(self):
        """Read exact, active academic identities without answer/scoring data."""
        c = self._connect(writable=False)
        try:
            courses = tuple(dict(r) for r in c.execute(
                "SELECT id,code,name FROM courses WHERE deleted_at IS NULL AND status='active' ORDER BY code,id"))
            topics = tuple(dict(r) for r in c.execute(
                "SELECT t.id,t.course_id,t.name FROM topics t JOIN courses c ON c.id=t.course_id "
                "WHERE t.deleted_at IS NULL AND c.deleted_at IS NULL AND c.status='active' ORDER BY c.code,t.name,t.id"))
            assessments = tuple(dict(r) for r in c.execute(
                "SELECT a.id,a.course_id,a.title,a.assessment_type,a.due_on FROM assessments a JOIN courses c ON c.id=a.course_id "
                "WHERE a.deleted_at IS NULL AND c.deleted_at IS NULL AND c.status='active' ORDER BY COALESCE(a.due_on,'9999'),a.id"))
            return {'courses':courses,'topics':topics,'assessments':assessments}
        except sqlite3.Error as error:
            raise PlannerTaskRepositoryError('Academic catalogue is unavailable.') from error
        finally:
            c.close()

    @staticmethod
    def _validate_capture_references(c, row):
        course_id = row.get('course_id')
        if not course_id:
            if row.get('topic_id') or row.get('assessment_id'):
                raise PlannerTaskRepositoryConflictError('Choose a course for the selected topic or assessment.')
            return
        if c.execute("SELECT 1 FROM courses WHERE id=? AND deleted_at IS NULL AND status='active'", (course_id,)).fetchone() is None:
            raise PlannerTaskRepositoryConflictError('Choose an active course from the catalogue.')
        for field, table in (('topic_id','topics'),('assessment_id','assessments')):
            if row.get(field) and c.execute(
                    "SELECT 1 FROM " + table + " WHERE id=? AND course_id=? AND deleted_at IS NULL",
                    (row[field],course_id)).fetchone() is None:
                raise PlannerTaskRepositoryConflictError('Selected topic or assessment does not belong to this active course.')

    def create_task(self, row, *, study_context=None, source_refs=()):
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                self._validate_capture_references(c, row)
                if source_refs:
                    prior = c.execute('SELECT * FROM planner_tasks WHERE id=?', (row['id'],)).fetchone()
                    if prior is not None:
                        if any(prior[k] != row.get(k) for k in ('title','description','course_id','topic_id','estimated_minutes','priority','due_on')):
                            raise PlannerTaskRepositoryConflictError('This source study intent has a different saved choice.')
                        return dict(prior)
                if study_context is not None:
                    if (row.get('course_id') != study_context['course_id'] or
                            row.get('topic_id') != study_context['topic_id']):
                        raise PlannerTaskRepositoryConflictError('Study identity changed.')
                    active = c.execute(
                        'SELECT t.name FROM topics t JOIN courses c ON c.id=t.course_id '
                        'WHERE c.id=? AND t.id=? AND c.deleted_at IS NULL AND t.deleted_at IS NULL',
                        (study_context['course_id'],study_context['topic_id'])).fetchone()
                    if active is None or (study_context.get('topic_name') is not None and
                            active['name'] != study_context['topic_name']):
                        raise PlannerTaskRepositoryConflictError('Course/topic context changed. Preview again.')
                    existing = c.execute('SELECT * FROM planner_tasks WHERE id=?',(row['id'],)).fetchone()
                    if existing is not None:
                        keys=('title','description','course_id','topic_id','estimated_minutes','priority','due_on')
                        if any(existing[k]!=row.get(k) for k in keys):
                            raise PlannerTaskRepositoryConflictError('This study intent has a different saved context.')
                        return dict(existing)
                c.execute(
                    "INSERT INTO planner_tasks "
                    "(id,source_import_id,external_id,title,description,priority,"
                    "course_id,topic_id,assessment_id,estimated_minutes,due_on,"
                    "preferred_day,preferred_window,rollover_policy,status,"
                    "manual_revision,created_at,updated_at,completed_at,archived_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["id"], row.get("source_import_id"), row.get("external_id"),
                        row["title"], row.get("description", ""), row["priority"],
                        row.get("course_id"), row.get("topic_id"), row.get("assessment_id"),
                        row.get("estimated_minutes"), row.get("due_on"),
                        row.get("preferred_day"), row.get("preferred_window"),
                        row.get("rollover_policy", ""), row.get("status", "backlog"),
                        int(row.get("manual_revision", 0)), row["created_at"], row["updated_at"],
                        row.get("completed_at"), row.get("archived_at"),
                    ),
                )
                if source_refs and c.execute("SELECT 1 FROM sqlite_master WHERE name='planner_task_sources'").fetchone():
                    for ref in source_refs:
                        if ref.get('owner') not in {'academic','learning','native_note','obsidian','library','tutor'}:
                            raise PlannerTaskRepositoryConflictError('Unknown source owner.')
                        c.execute('INSERT INTO planner_task_sources(task_id,owner,kind,identifier,revision_key,sha256,mapping_status) VALUES(?,?,?,?,?,?,?)',
                                  (row['id'],ref['owner'],ref['kind'],ref['identifier'],str(ref.get('revision_key','')),ref.get('sha256'),ref.get('mapping_status','unreviewed')))
        except sqlite3.Error as error:
            raise PlannerTaskRepositoryError("The task could not be saved.") from error
        finally:
            c.close()
        return self.get_task(row["id"])

    def update_task(self, task_id, fields, *, mark_manual=True, expected=None):
        allowed = {
            "title", "description", "priority", "course_id", "topic_id",
            "assessment_id", "estimated_minutes", "due_on", "preferred_day",
            "preferred_window", "rollover_policy", "status", "completed_at",
            "archived_at", "updated_at",
        }
        values = {k: v for k, v in fields.items() if k in allowed}
        if not values:
            return self.get_task(task_id)
        assignments = ["{}=?".format(k) for k in values]
        params = list(values.values())
        if mark_manual:
            assignments.append("manual_revision=manual_revision+1")
        params.append(task_id)
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                current = c.execute('SELECT * FROM planner_tasks WHERE id=?', (task_id,)).fetchone()
                if current is None:
                    raise PlannerTaskRepositoryNotFoundError('Planner task was not found.')
                if expected is not None and any(current[k] != expected[k] for k in ('status','manual_revision','updated_at')):
                    raise PlannerTaskRepositoryConflictError('Task changed. Refresh before editing.')
                if 'revision' in current.keys():
                    assignments.append('revision=revision+1')
                cur = c.execute(
                    "UPDATE planner_tasks SET {} WHERE id=?".format(", ".join(assignments)),
                    tuple(params),
                )
                if cur.rowcount != 1:
                    raise PlannerTaskRepositoryNotFoundError("Planner task was not found.")
        finally:
            c.close()
        return self.get_task(task_id)

    def create_or_replace_imported_task(self, row):
        """Upsert a source-managed task only when the existing row was not manually revised."""
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                existing = c.execute(
                    "SELECT * FROM planner_tasks WHERE id=?", (row["id"],)
                ).fetchone()
                if existing is not None and int(existing["manual_revision"]) > 0:
                    raise PlannerTaskRepositoryError(
                        "An imported task has manual edits and requires reconciliation."
                    )
                if existing is None:
                    c.execute(
                        "INSERT INTO planner_tasks "
                        "(id,source_import_id,external_id,title,description,priority,"
                        "course_id,topic_id,assessment_id,estimated_minutes,due_on,"
                        "preferred_day,preferred_window,rollover_policy,status,"
                        "manual_revision,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)",
                        (
                            row["id"], row.get("source_import_id"), row.get("external_id"),
                            row["title"], row.get("description",""), row["priority"],
                            row.get("course_id"), row.get("topic_id"), row.get("assessment_id"),
                            row.get("estimated_minutes"), row.get("due_on"),
                            row.get("preferred_day"), row.get("preferred_window"),
                            row.get("rollover_policy",""), row.get("status","backlog"),
                            row["created_at"], row["updated_at"],
                        ),
                    )
                else:
                    c.execute(
                        "UPDATE planner_tasks SET source_import_id=?,external_id=?,title=?,"
                        "description=?,priority=?,course_id=?,topic_id=?,assessment_id=?,"
                        "estimated_minutes=?,due_on=?,preferred_day=?,preferred_window=?,"
                        "rollover_policy=?,status=?,updated_at=? WHERE id=?",
                        (
                            row.get("source_import_id"), row.get("external_id"), row["title"],
                            row.get("description",""), row["priority"], row.get("course_id"),
                            row.get("topic_id"), row.get("assessment_id"),
                            row.get("estimated_minutes"), row.get("due_on"),
                            row.get("preferred_day"), row.get("preferred_window"),
                            row.get("rollover_policy",""),
                            existing["status"] if existing["status"] in ('completed','archived','in_progress','skipped') else row.get("status","backlog"),
                            row["updated_at"], row["id"],
                        ),
                    )
        finally:
            c.close()
        return self.get_task(row["id"])
