"""One transaction owns task commands, work receipts and agenda projections."""
from datetime import datetime
import hashlib
import json
import uuid
from .connection import transaction
from .planner_task_repository import (
    SQLitePlannerTaskRepository, PlannerTaskRepositoryConflictError,
    PlannerTaskRepositoryNotFoundError,
)

CONFLICT = PlannerTaskRepositoryConflictError


class SQLitePlannerExecutionRepository(SQLitePlannerTaskRepository):
    def _execute(self, task_id, *, expected_revision, command_id, action,
                 occurred_at, agenda_item_id=None, actual_minutes=None, note='', supersedes_id=None):
        try:
            if str(uuid.UUID(str(command_id))) != command_id:
                raise ValueError()
            if type(expected_revision) is not int or expected_revision < 0:
                raise ValueError()
            instant = datetime.fromisoformat(occurred_at.replace('Z', '+00:00'))
            if instant.tzinfo is None:
                raise ValueError()
            if actual_minutes is not None and (type(actual_minutes) is not int or not 0 <= actual_minutes <= 1440):
                raise ValueError()
            if len(note) > 4000:
                raise ValueError()
        except (ValueError, AttributeError, TypeError) as error:
            raise CONFLICT('Command identity, revision, time or minutes is invalid.') from error
        payload = dict(task_id=task_id, expected_revision=expected_revision, action=action,
                       agenda_item_id=agenda_item_id, actual_minutes=actual_minutes, note=note,
                       supersedes_id=supersedes_id)
        # Transition occurrence is server-assigned. Replaying a browser command
        # after another request must return its original receipt and timestamp.
        if action == 'log_progress':
            payload['occurred_at'] = occurred_at
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        c = self._connect(writable=True)
        try:
            with transaction(c, immediate=True):
                old = c.execute('SELECT payload_hash,result_json FROM planner_command_receipts WHERE command_id=?', (command_id,)).fetchone()
                if old:
                    if old['payload_hash'] != digest:
                        raise CONFLICT('This command ID already has a different payload.')
                    return json.loads(old['result_json'])
                row = c.execute('SELECT * FROM planner_tasks WHERE id=?', (task_id,)).fetchone()
                if row is None:
                    raise PlannerTaskRepositoryNotFoundError('Task was not found.')
                if row['revision'] != expected_revision:
                    raise CONFLICT('Task changed. Refresh before recording work.')
                from personal_learning_assistant.services.operational_task_service import _ALLOWED
                if action == 'log_progress':
                    if row['status'] in {'archived', 'completed', 'skipped'} and supersedes_id is None:
                        raise CONFLICT('Terminal tasks cannot record new work.')
                    status = row['status'] if supersedes_id else 'in_progress'
                    if actual_minutes is None:
                        raise CONFLICT('Enter the minutes explicitly, including zero if applicable.')
                else:
                    status = action
                    if status not in _ALLOWED.get(row['status'], set()):
                        raise CONFLICT('This task transition is no longer available.')
                item = None
                if agenda_item_id:
                    item = c.execute('SELECT i.*,a.status AS agenda_status FROM daily_agenda_items i JOIN daily_agendas a ON a.id=i.agenda_id WHERE i.id=?', (agenda_item_id,)).fetchone()
                    if (item is None or item['source_type'] != 'planner_task' or item['source_id'] != task_id
                            or (item['agenda_status'] not in {'approved', 'active'} and not supersedes_id)
                            or (item['status'] in {'completed', 'moved', 'skipped'} and not supersedes_id)):
                        raise CONFLICT('Agenda source changed. Refresh before recording work.')
                if supersedes_id:
                    previous = c.execute('SELECT * FROM planner_work_logs WHERE id=? AND task_id=?', (supersedes_id, task_id)).fetchone()
                    if (previous is None or previous['agenda_item_id'] != agenda_item_id or
                            c.execute('SELECT 1 FROM planner_work_logs WHERE supersedes_id=?', (supersedes_id,)).fetchone()):
                        raise CONFLICT('Work log correction is stale or belongs to another source.')
                if item and item['actual_minutes'] is not None and not c.execute('SELECT 1 FROM planner_work_logs WHERE agenda_item_id=?', (agenda_item_id,)).fetchone():
                    # Preserve the owner-recorded legacy total exactly once when
                    # crossing from aggregate minutes to append-only logs.
                    try:
                        prior_instant = datetime.fromisoformat(item['updated_at'].replace('Z', '+00:00'))
                        if prior_instant.tzinfo is None:
                            raise ValueError()
                    except (ValueError, AttributeError) as error:
                        raise CONFLICT('Legacy effort has no reliable timestamp; review it before adding a session.') from error
                    c.execute("INSERT INTO planner_work_logs(id,task_id,agenda_item_id,actual_minutes,occurred_at,note,evidence_label) VALUES(?,?,?,?,?,?,'legacy_self_reported')",
                              ('legacy-agenda:'+agenda_item_id, task_id, agenda_item_id, item['actual_minutes'], item['updated_at'], 'Existing agenda total retained during work-log adoption.'))
                if actual_minutes is not None:
                    c.execute('INSERT INTO planner_work_logs(id,task_id,agenda_item_id,actual_minutes,occurred_at,note,supersedes_id) VALUES(?,?,?,?,?,?,?)',
                              (command_id, task_id, agenda_item_id, actual_minutes, occurred_at, note, supersedes_id))
                result = dict(command_id=command_id, task_id=task_id, prior_revision=expected_revision,
                              new_revision=expected_revision+1, action=action, occurred_at=occurred_at, status=status)
                changed = c.execute("UPDATE planner_tasks SET status=?,revision=revision+1,manual_revision=manual_revision+1,updated_at=?,completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END,archived_at=CASE WHEN ?='archived' THEN ? ELSE archived_at END WHERE id=? AND revision=?",
                                    (status, occurred_at, action, occurred_at, action, occurred_at, task_id, expected_revision))
                if changed.rowcount != 1:
                    raise CONFLICT('Task changed while recording work.')
                if item:
                    total = c.execute('SELECT SUM(l.actual_minutes) FROM planner_work_logs l WHERE l.agenda_item_id=? AND NOT EXISTS(SELECT 1 FROM planner_work_logs n WHERE n.supersedes_id=l.id)', (agenda_item_id,)).fetchone()[0]
                    c.execute('UPDATE daily_agenda_items SET status=?,actual_minutes=?,completed_at=?,updated_at=? WHERE id=?',
                              (status, total, item['completed_at'] if supersedes_id else occurred_at if status == 'completed' else None, occurred_at, agenda_item_id))
                c.execute('INSERT INTO planner_command_receipts VALUES(?,?,?,?,?,?,?,?)',
                          (command_id, digest, task_id, expected_revision, expected_revision+1, action, occurred_at, json.dumps(result, sort_keys=True)))
                return result
        finally:
            c.close()

    def transition_task(self, task_id, *, expected_revision, command_id, target_status, occurred_at, agenda_item_id=None, actual_minutes=None, note=''):
        return self._execute(task_id, expected_revision=expected_revision, command_id=command_id,
                             action=target_status, occurred_at=occurred_at, agenda_item_id=agenda_item_id,
                             actual_minutes=actual_minutes, note=note)

    def log_progress(self, task_id, *, expected_revision, command_id, occurred_at, actual_minutes, agenda_item_id=None, note='', supersedes_id=None):
        return self._execute(task_id, expected_revision=expected_revision, command_id=command_id,
                             action='log_progress', occurred_at=occurred_at, agenda_item_id=agenda_item_id,
                             actual_minutes=actual_minutes, note=note, supersedes_id=supersedes_id)
