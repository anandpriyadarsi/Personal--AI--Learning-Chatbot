"""Content-free lifecycle browsing; never changes an assessment or attempt."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import config
from personal_learning_assistant.repositories.sqlite.assessment_workspace_repository import SQLiteAssessmentWorkspaceRepository
from personal_learning_assistant.services.assessment_runner_service import _marks_text


class AssessmentWorkspaceUnavailableError(RuntimeError):
    pass


class AssessmentWorkspaceNotFoundError(RuntimeError):
    pass


STATES = (('', 'All'), ('preparation', 'To prepare'), ('ready', 'Ready'),
          ('active', 'In progress'), ('results', 'Results'), ('rejected', 'Rejected'))
KINDS = (('', 'All types'), ('quiz', 'Quiz'), ('exam', 'Exam'), ('test', 'Test'))
PAGE_SIZE = 20


def _kind(row):
    if row.get('workspace_kind') in {'quiz', 'exam', 'test'}:
        return row['workspace_kind']
    value = row.get('assessment_type')
    return 'quiz' if value == 'quiz' else 'exam' if value in {'midsem', 'endsem', 'previous_paper'} else 'test'


class AssessmentWorkspaceService:
    def __init__(self, database_path, now_fn=None):
        self.database_path = Path(database_path)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def _repository(self):
        path = self.database_path
        if not path.is_file() or path.is_symlink():
            raise AssessmentWorkspaceUnavailableError('Assessment storage is unavailable.')
        try:
            uri = 'file:{}?mode=ro'.format(quote(path.resolve().as_posix(), safe='/'))
            db = sqlite3.connect(uri, uri=True, isolation_level=None)
            try:
                db.execute('PRAGMA query_only=ON')
                yield SQLiteAssessmentWorkspaceRepository(db)
            finally:
                db.close()
        except sqlite3.Error as error:
            raise AssessmentWorkspaceUnavailableError('Assessment workspace requires the current database migrations.') from error

    def _decorate(self, source):
        row = dict(source)
        sid = quote(str(row.get('session_id') or ''), safe='')
        aid = quote(str(row.get('assessment_id') or ''), safe='')
        row['kind'] = _kind(row)
        row['max_marks'] = _marks_text(row.get('max_marks_milli'))
        row['attempt_count'] = int(row.get('attempt_count') or 0)
        if row['entry_type'] == 'package':
            state = 'rejected' if row['status'] == 'rejected' else 'preparation'
            label = 'Rejected' if state == 'rejected' else 'Blind preflight'
            action = 'View package' if state == 'rejected' else 'Review safely'
            url = '/assessments/import/' + quote(str(row['id']), safe='') + '/review'
        elif sid:
            if row['session_status'] == 'active':
                expires = datetime.fromisoformat(row['expires_at'].replace('Z', '+00:00'))
                state = 'active' if expires > self.now_fn() else 'time_ended'
                label = 'In progress' if state == 'active' else 'Time ended'
                action = 'Resume test' if state == 'active' else 'Finish timed-out attempt'
                url = '/assessments/sessions/' + sid
            elif not row.get('evaluation_status'):
                state, label, action = 'needs_evaluation', 'Ready to evaluate', 'Evaluate responses'
                url = '/assessments/sessions/' + sid + '/summary'
            else:
                complete = row['evaluation_status'] == 'confirmed'
                state = 'completed' if complete else 'needs_grading'
                label = 'Completed' if complete else 'Grading needs review'
                action = 'View results' if complete else 'Review grading'
                url = '/assessments/sessions/' + sid + '/evaluation'
        else:
            state, label, action = 'ready', 'Ready to take', 'Open instructions'
            url = '/assessments/tests/' + aid
        row.update(state=state, state_label=label, action_label=action, action_url=url)
        row['category'] = ('active' if state in {'active', 'time_ended'} else
                           'results' if state in {'completed', 'needs_grading', 'needs_evaluation'} else state)
        return row

    @staticmethod
    def _paginate(rows, page):
        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1
        pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        return {'rows': tuple(rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]),
                'total': len(rows), 'page': page, 'pages': pages,
                'has_previous': page > 1, 'has_next': page < pages}

    def library(self, query='', course_id='', kind='', state='', page=1, assessment_id=''):
        query = str(query or '').strip()[:200]
        kind = kind if kind in dict(KINDS) else ''
        state = state if state in dict(STATES) else ''
        with self._repository() as repository:
            courses = repository.courses()
            rows = [self._decorate(row) for row in repository.rows()]
        rows.sort(key=lambda x: (str(x.get('updated_at') or ''), x['id']), reverse=True)
        priority = {'active': 0, 'time_ended': 1, 'needs_grading': 2,
                    'needs_evaluation': 3, 'preparation': 4, 'ready': 5}
        actionable = [row for row in rows if row['state'] in priority]
        continuation = min(actionable, key=lambda row: priority[row['state']]) if actionable else None
        filtered = [row for row in rows
                    if (not course_id or row['course_id'] == course_id)
                    and (not kind or row['kind'] == kind)
                    and (not assessment_id or row.get('assessment_id') == assessment_id)
                    and (not query or query.casefold() in ' '.join(str(row.get(k) or '') for k in ('title','course_code','course_name')).casefold())]
        counts = {key: sum(row['category'] == key for row in filtered) for key, _ in STATES if key}
        filtered = [row for row in filtered if (row['category'] == state if state else row['category'] != 'rejected')]
        return {'available': True, **self._paginate(filtered, page), 'courses': courses,
                'query': query, 'course_id': str(course_id or ''), 'kind': kind, 'state': state,
                'states': STATES, 'kinds': KINDS, 'counts': counts, 'continuation': continuation}

    def history(self, assessment_id, page=1):
        with self._repository() as repository:
            assessment = next((row for row in repository.rows()
                               if row.get('assessment_id') == assessment_id), None)
            if assessment is None:
                raise AssessmentWorkspaceNotFoundError('Assessment not found.')
            rows = [self._decorate(row) for row in repository.history(assessment_id)]
        return {'available': True, 'assessment': self._decorate(assessment), **self._paginate(rows, page)}


def build_assessment_workspace_service(database_path=None):
    return AssessmentWorkspaceService(database_path or config.DATABASE_PATH)
