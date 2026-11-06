"""Coding data in the canonical Tutor connection and atomic exchange."""
import json
import uuid
from personal_learning_assistant.domain.coding_models import CodingError, canonical
from personal_learning_assistant.services.tutor_session_service import _utc_now


class SQLiteTutorCodingRepository:
    def __init__(self, tutor_repository):
        self.tutor = tutor_repository
        self.connection = tutor_repository.connection

    def available(self):
        tables = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {'tutor_coding_tasks', 'tutor_coding_turn_context'} <= tables

    def require(self, sid, *, active=True):
        row = self.connection.execute('SELECT status FROM tutor_sessions WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise CodingError('not_found', 'Tutor session was not found.', 404)
        if active and row[0] != 'active':
            raise CodingError('inactive_session', 'This session is read-only.', 409)
        if not self.available():
            raise CodingError('schema_unavailable', 'Coding Studio needs explicit activation. See the Windows setup guide.', 503)

    @staticmethod
    def view(row):
        result = dict(row)
        result['snapshot'] = json.loads(result.pop('snapshot_json'))
        result.pop('creation_digest', None)
        return result

    def tasks(self, sid):
        self.require(sid, active=False)
        return [self.view(r) for r in self.connection.execute(
            'SELECT * FROM tutor_coding_tasks WHERE session_id=? AND archived_at IS NULL ORDER BY created_at,id', (sid,))]

    def task(self, sid, tid, *, active=True):
        self.require(sid, active=active)
        row = self.connection.execute('SELECT * FROM tutor_coding_tasks WHERE id=? AND session_id=?', (tid,sid)).fetchone()
        if row is None:
            raise CodingError('not_found', 'Coding task was not found in this conversation.', 404)
        if active and row['archived_at']:
            raise CodingError('archived_task', 'This task is archived. Start a new task.', 409)
        return self.view(row)

    def create(self, sid, data, request_digest):
        self.require(sid)
        with self.tutor._write_transaction():
            old = self.connection.execute('SELECT * FROM tutor_coding_tasks WHERE session_id=? AND creation_request_id=?',
                                          (sid,data['request_id'])).fetchone()
            if old:
                if old['creation_digest'] != request_digest:
                    raise CodingError('request_conflict', 'This request identity belongs to another task.', 409)
                return self.view(old), False
            tid, now = str(uuid.uuid4()), _utc_now()
            self.connection.execute('INSERT INTO tutor_coding_tasks VALUES (?,?,1,?,?,?,?,?,?,?,?,?,NULL)',
                (tid,sid,data['language'],data['title'],data['request_id'],request_digest,
                 data['template_id'] or None,1 if data['template_id'] else None,
                 canonical(data['snapshot']),now,now))
        return self.task(sid,tid), True

    def update(self, sid, tid, revision, *, title=None, snapshot=None, archive=False):
        self.task(sid,tid)
        with self.tutor._write_transaction():
            current = self.task(sid,tid)
            if current['revision'] != revision:
                raise CodingError('stale_task', 'Review the updated task and retry.', 409)
            now = _utc_now()
            changed = self.connection.execute('UPDATE tutor_coding_tasks SET revision=revision+1,title=?,snapshot_json=?,updated_at=?,archived_at=? WHERE id=? AND session_id=? AND revision=? AND archived_at IS NULL',
                (title if title is not None else current['title'],canonical(snapshot if snapshot is not None else current['snapshot']),
                 now,now if archive else None,tid,sid,revision)).rowcount
            if changed != 1:
                raise CodingError('stale_task', 'Review the updated task and retry.', 409)
        return self.task(sid,tid,active=not archive)

    def receipt(self, sid, tid, request_id, request_digest):
        self.task(sid,tid,active=False)
        row = self.connection.execute('SELECT * FROM tutor_coding_turn_context WHERE task_id=? AND request_id=?', (tid,request_id)).fetchone()
        if row is None:
            return None
        if row['request_digest'] != request_digest:
            raise CodingError('request_conflict', 'This request identity has different code, action or permissions.', 409)
        return {'user_turn_id':row['user_turn_id'], 'assistant_turn_id':row['assistant_turn_id'], 'replayed':True}

    def append_context(self, tid, data, request_digest, source_snapshot, user, assistant):
        # Caller must already be writing turns in the SAME Tutor atomic exchange.
        if not self.tutor._exchange or not self.tutor._exchange['started']:
            raise RuntimeError('coding context requires the Tutor exchange transaction')
        self.connection.execute('INSERT INTO tutor_coding_turn_context VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (user.turn_id,assistant.turn_id,tid,data['request_id'],request_digest,data['action'],data['hint_level'],
             int(data['full_solution']),canonical(data,24576),canonical(source_snapshot,16384),'ai_feedback',assistant.created_at))

    def history(self, tid, *, allow_solution=False):
        rows = self.connection.execute('SELECT c.*,u.content AS user_content,a.content AS assistant_content FROM tutor_coding_turn_context c JOIN tutor_turns u ON u.id=c.user_turn_id JOIN tutor_turns a ON a.id=c.assistant_turn_id WHERE c.task_id=? ORDER BY u.ordinal DESC', (tid,)).fetchall()
        selected, size, omitted = [], 0, False
        for row in rows:
            if row['full_solution'] and not allow_solution:
                omitted = True
                continue
            request = json.loads(row['request_json'])
            pair = {'student': {key:request[key] for key in ('action','topic','message','code','error','attempt')}, 'tutor': row['assistant_content']}
            cost = len(canonical(pair))
            if size + cost > 7900:
                omitted = True
                break
            size += cost
            selected.append(pair)
        return {'exchanges':list(reversed(selected)), 'older_context_omitted':omitted}

    def turn_context(self, sid):
        if not self.available():
            return {}
        result = {}
        for row in self.connection.execute('SELECT c.* FROM tutor_coding_turn_context c JOIN tutor_coding_tasks t ON t.id=c.task_id WHERE t.session_id=?', (sid,)):
            data = json.loads(row['request_json'])
            result[row['user_turn_id']] = {'action':row['action'],'request':data,'task_id':row['task_id'],'kind':'student_provided_unverified'}
            result[row['assistant_turn_id']] = {'action':row['action'],'task_id':row['task_id'],'kind':'ai_feedback','full_solution':bool(row['full_solution'])}
        return result
