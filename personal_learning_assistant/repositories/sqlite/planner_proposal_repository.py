"""Append-only proposal revisions, written only with an explicit draft save."""
import json
import sqlite3
import uuid

from personal_learning_assistant.repositories.sqlite.daily_agenda_repository import (
    _open, DailyAgendaRepositoryError, DailyAgendaRepositoryConflictError,
)


class SQLitePlannerProposalRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def latest(self, agenda_date):
        c = _open(self.database_path, writable=False)
        try:
            # Optional activation: reading an older database must never migrate it.
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planner_proposals'").fetchone():
                return None
            row = c.execute('SELECT * FROM planner_proposals WHERE agenda_date=? ORDER BY revision DESC LIMIT 1', (agenda_date,)).fetchone()
            return self._context(row)
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise DailyAgendaRepositoryError('Saved proposal context is unavailable.') from error
        finally:
            c.close()

    def by_command(self, command_id):
        c = _open(self.database_path, writable=False)
        try:
            row = c.execute('SELECT * FROM planner_proposals WHERE command_id=?', (command_id,)).fetchone()
            return self._context(row)
        except sqlite3.Error as error:
            raise DailyAgendaRepositoryError('Proposal persistence requires the PAO migration.') from error
        finally:
            c.close()

    @staticmethod
    def _context(row):
        if row is None:
            return None
        context = json.loads(row['context_json'])
        return {**context, 'proposal_id': row['id'], 'revision': row['revision'], 'command_id': row['command_id']}

    @staticmethod
    def append(c, agenda_date, context, *, created_at):
        """Caller owns the draft transaction, so draft and context commit together."""
        try:
            command_id = context['command_id']
            if c.execute('SELECT 1 FROM planner_proposals WHERE command_id=?', (command_id,)).fetchone():
                raise DailyAgendaRepositoryConflictError('Proposal command was already saved.')
            revision = c.execute('SELECT COALESCE(MAX(revision),0)+1 FROM planner_proposals WHERE agenda_date=?', (agenda_date,)).fetchone()[0]
            c.execute('INSERT INTO planner_proposals (id,agenda_date,revision,command_id,context_json,created_at) VALUES (?,?,?,?,?,?)',
                      (str(uuid.uuid4()), agenda_date, revision, command_id, json.dumps(context, sort_keys=True), created_at))
        except sqlite3.Error as error:
            raise DailyAgendaRepositoryError('Proposal persistence requires the PAO migration.') from error
