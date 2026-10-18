"""Bounded read-side academic composition. No migrations, provider calls or writes.

Evaluated marks are session outcomes, never independence or topic mastery.
Learning Studio and Notes retain their separate existing read projections.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .academic_wal_snapshot import (
    AcademicSnapshotUnavailable, AuthorizedAcademicSnapshot, MAX_SNAPSHOT_BYTES, SQLITE_HEADER,
)

LIMIT = 100
POLICY = 'planning-analysis-read-v2.1'


class AcademicOverviewService:
    def __init__(self, database_path, *, now=None, local_timezone='Asia/Kolkata',
                 wal_snapshot_provider=None, max_snapshot_age_seconds=120):
        self.path = Path(database_path)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.zone = ZoneInfo(local_timezone)
        if (type(max_snapshot_age_seconds) is not int
                or not 1 <= max_snapshot_age_seconds <= 3600):
            raise ValueError('Snapshot maximum age must be between 1 and 3600 seconds.')
        if wal_snapshot_provider is not None and not callable(wal_snapshot_provider):
            raise ValueError('WAL snapshot provider must be callable.')
        self.wal_snapshot_provider = wal_snapshot_provider
        self.max_snapshot_age_seconds = max_snapshot_age_seconds

    def _open_authorized_wal_snapshot(self, view, now):
        """Read an authoritative owner's memory image, never the live -wal/-shm."""
        if self.wal_snapshot_provider is None:
            raise AcademicSnapshotUnavailable('No academic snapshot publisher configured.')
        try:
            snapshot = self.wal_snapshot_provider()
        except Exception as error:
            raise AcademicSnapshotUnavailable('The academic owner snapshot feed is unavailable.') from error
        if not isinstance(snapshot, AuthorizedAcademicSnapshot):
            raise AcademicSnapshotUnavailable('Snapshot must be issued by the academic owner.')
        if snapshot.database_identity != str(self.path.absolute().resolve(strict=True)):
            raise AcademicSnapshotUnavailable('Snapshot source identity does not match.')
        if not isinstance(snapshot.published_at, datetime) or snapshot.published_at.tzinfo is None:
            raise AcademicSnapshotUnavailable('Snapshot timestamp is not authoritative.')
        age = (now.astimezone(timezone.utc) -
               snapshot.published_at.astimezone(timezone.utc)).total_seconds()
        if age < -5 or age > self.max_snapshot_age_seconds:
            raise AcademicSnapshotUnavailable('Snapshot is stale or from the future.')
        payload = snapshot.payload
        if (type(payload) is not bytes or len(payload) < 100 or
                len(payload) > MAX_SNAPSHOT_BYTES or not payload.startswith(SQLITE_HEADER)
                or payload[18:20] != bytes((1, 1))
                or type(snapshot.revision) is not int or snapshot.revision <= 0):
            raise AcademicSnapshotUnavailable('Snapshot integrity or revision is invalid.')
        con = sqlite3.connect(':memory:')
        try:
            con.deserialize(payload)
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA query_only=ON')
            con.execute('BEGIN')
        except (sqlite3.Error, ValueError):
            con.close()
            raise AcademicSnapshotUnavailable('The published snapshot is unreadable.')
        view['source_snapshot'] = {
            'mode': 'owner_published_wal',
            'revision': snapshot.revision,
            'published_at': snapshot.published_at.astimezone(timezone.utc).isoformat(),
            'age_seconds': max(0, int(age)),
            'provenance': 'Committed academic-owner SQLite online backup',
        }
        view['limits'].append('Academic evidence is current only through the last committed owner publication.')
        return con

    def overview(self, *, course='', days=28, evidence='all'):
        course = str(course).strip().upper()
        try:
            days = int(days)
        except (TypeError, ValueError) as error:
            raise ValueError('Choose 7, 28 or 90 days.') from error
        if days not in (7, 28, 90) or evidence not in ('all', 'evaluated', 'self_reported', 'pending'):
            raise ValueError('Choose a supported time window and evidence category.')
        if course and not re.fullmatch(r'[A-Z0-9_-]{1,32}', course):
            raise ValueError('Invalid course code.')
        now = self.now()
        if now.tzinfo is None:
            raise ValueError('The academic clock must include a timezone.')
        local = now.astimezone(self.zone)
        start = local.date() - timedelta(days=days-1)
        lower = datetime.combine(start, datetime.min.time(), self.zone).astimezone(timezone.utc).isoformat()
        upper = now.astimezone(timezone.utc).isoformat()
        view = {
            'available': False, 'date': local.date().isoformat(), 'timezone': str(self.zone),
            'as_of': upper, 'policy_version': POLICY,
            'filters': {'course': course, 'days': days, 'evidence': evidence},
            'courses': [], 'assessments': [], 'tasks': [], 'topics': [],
            'effort': {'planned_minutes': None, 'actual_minutes': None, 'recorded_items': 0,
                       'total_items': 0, 'completed_items': 0},
            'summary': dict.fromkeys(('open_tasks','overdue_tasks','evaluated_sessions','self_reported_sessions','pending_sessions')),
            'source_status': {}, 'source_snapshot': None,
            'limits': ['Evaluated performance does not establish independent work or mastery.',
                       'Topic mapping review is not established; recovery candidates require manual review.',
                       'Learning practice and Notes below use their own source scope; these filters apply to Assessment records.'],
        }
        path = self.path
        if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.absolute().parents):
            view['limits'].append('Academic database unavailable. No database was created.')
            return view
        # Direct query-only WAL reads can still update the shared-memory index.
        # No file-based SQLite connection is opened on the WAL read path.
        try:
            # A configured owner feed never even reads the source header.
            # For unconfigured installs, inspect the 20-byte header and refuse
            # WAL databases instead of opening their shared-memory index.
            if self.wal_snapshot_provider is not None:
                source_is_wal = True
            else:
                with path.open('rb') as stream:
                    header = stream.read(20)
                source_is_wal = len(header) >= 20 and header[18:20] == bytes((2, 2))
            if source_is_wal:
                try:
                    con = self._open_authorized_wal_snapshot(view, now)
                except (AcademicSnapshotUnavailable, OSError, sqlite3.Error, ValueError):
                    view['source_status']['academic_snapshot'] = 'unavailable'
                    view['limits'].append(
                        'Live WAL evidence unavailable: a fresh, owner-published committed snapshot '
                        'is required. This reader did not open the database, WAL or SHM with SQLite.')
                    return view
            else:
                con = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)
                con.row_factory = sqlite3.Row
                con.execute('PRAGMA query_only=ON')
                con.execute('BEGIN')
            try:
                self._courses(con, view)
                self._assessments(con, view, lower, upper)
                self._topics(con, view, lower, upper)
                self._tasks(con, view)
                self._effort(con, view, start.isoformat())
                view['available'] = any(s == 'available' for s in view['source_status'].values())
            finally:
                con.close()
        except (sqlite3.Error, OSError):
            view['limits'].append('Academic storage could not be read. Existing records were not changed.')
        return view

    @staticmethod
    def _read(con, view, source, sql, params=()):
        try:
            rows = [dict(row) for row in con.execute(sql, params)]
            view['source_status'][source] = 'available'
            return rows
        except sqlite3.Error:
            view['source_status'][source] = 'unavailable'
            view['limits'].append(source.replace('_',' ').title()+' unavailable in this schema.')
            return None

    def _courses(self, con, view):
        rows = self._read(con, view, 'courses',
            'SELECT id,code,name FROM courses WHERE deleted_at IS NULL ORDER BY code LIMIT ?', (LIMIT+1,))
        if rows is not None:
            view['courses'] = rows[:LIMIT]
            if len(rows)>LIMIT: view['limits'].append('Course list limited to 100 records.')

    def _assessments(self, con, view, lower, upper):
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        has_papers = 'assessment_extended_self_reviews' in tables
        paper_exclusion = (" AND NOT EXISTS (SELECT 1 FROM assessment_extended_self_reviews p WHERE p.session_id=s.id) " if has_papers else '')
        rows = self._read(con, view, 'assessments', '''
            SELECT s.id,s.title_snapshot title,s.course_code_snapshot course_code,s.status,s.mode,
                s.started_at,s.submitted_at,s.question_count,s.max_marks_milli,
                e.id evaluation_id,e.status evaluation_status,e.updated_at evidence_at,
                COUNT(r.id) evaluated_count, SUM(r.awarded_marks_milli) earned_milli,
                SUM(CASE WHEN r.status IN ('confirmed','auto_confirmed') AND
                    r.awarded_marks_milli IS NOT NULL THEN 1 ELSE 0 END) final_count,
                SUM(CASE WHEN julianday(r.updated_at)<=julianday(?) AND
                    julianday(r.updated_at)>=julianday(s.started_at) THEN 1 ELSE 0 END) dated_count,
                SUM(r.max_marks_milli) evaluated_max,
                SUM(CASE WHEN r.status IN ('confirmed','auto_confirmed') AND
                    r.awarded_marks_milli IS NOT NULL AND r.evaluator_type IN ('deterministic','teacher')
                    THEN 1 ELSE 0 END) confirmed_count,
                SUM(CASE WHEN r.evaluator_type='user' THEN 1 ELSE 0 END) self_count
            FROM assessment_test_sessions s
            LEFT JOIN assessment_session_evaluations e ON e.session_id=s.id
            LEFT JOIN assessment_response_evaluations r ON r.session_evaluation_id=e.id
            WHERE julianday(COALESCE(e.updated_at,s.started_at)) BETWEEN julianday(?) AND julianday(?)
              AND julianday(s.started_at)<=julianday(?)
              AND (?='' OR s.course_code_snapshot=? COLLATE NOCASE)
            '''+paper_exclusion+''' GROUP BY s.id ORDER BY julianday(COALESCE(e.updated_at,s.started_at)) DESC,s.id LIMIT ?''',
            (upper,lower,upper,upper,view['filters']['course'],view['filters']['course'],LIMIT+1))
        if rows is None: return
        if len(rows)>LIMIT: view['limits'].append('Assessment history limited to the latest 100 sessions; totals describe this sample.')
        selected = []
        for r in rows[:LIMIT]:
            terminal = r['status'] in ('submitted','expired')
            fully_evaluated = (terminal and r['evaluation_status']=='confirmed'
                and r['confirmed_count']==r['question_count'] and r['dated_count']==r['question_count']
                and r['evaluated_max']==r['max_marks_milli'])
            category = ('self_reported' if r['self_count']
                        else 'evaluated' if fully_evaluated else 'pending')
            scored = fully_evaluated or (category=='self_reported' and terminal
                       and r['final_count']==r['question_count'] and r['dated_count']==r['question_count']
                       and r['evaluated_max']==r['max_marks_milli'] and r['earned_milli'] is not None)
            row = {'id':r['id'], 'title':r['title'], 'course_code':r['course_code'],
                   'status':r['status'], 'mode':r['mode'], 'date':r['evidence_at'] or r['started_at'],
                   'earned':r['earned_milli']/1000 if scored else None,
                   'max_marks':r['max_marks_milli']/1000,'question_count':r['question_count'],
                   'category':category,'independence':'unknown','mapping_review':'not_established',
                   'source_refs':[r['id']]+([r['evaluation_id']] if r['evaluation_id'] else []),
                   'url':'/assessments/sessions/'+quote(r['id'],safe='')+('/evaluation' if terminal else '')}
            selected.append(row)
        if has_papers:
            from .academic_paper_projection import paper_rows
            try:
                papers, truncated = paper_rows(con, lower=lower, upper=upper, course=view['filters']['course'], limit=LIMIT)
                selected.extend(papers)
                if truncated: view['limits'].append('Paper review history limited to 100 sessions or the bounded question budget.')
            except sqlite3.Error:
                view['limits'].append('Paper self-reported evidence unavailable in this schema.')
        # Merge by absolute instant, then apply the shared sample and evidence filter.
        def timestamp(row):
            value = datetime.fromisoformat(row['date'].replace('Z','+00:00'))
            # SQLite julianday treats an offset-free canonical UTC value as UTC.
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        selected.sort(key=lambda row: (-timestamp(row), row['id']))
        selected = [row for row in selected[:LIMIT] if view['filters']['evidence'] in ('all',row['category'])]
        view['assessments'] = selected
        for category in ('evaluated','self_reported','pending'):
            view['summary'][category+'_sessions'] = sum(r['category']==category for r in selected)

    def _tasks(self, con, view):
        rows = self._read(con, view, 'tasks', '''SELECT t.id,t.title,t.priority,t.due_on,t.preferred_day,
            t.estimated_minutes,t.status,c.code course_code FROM planner_tasks t
            LEFT JOIN courses c ON c.id=t.course_id
            WHERE t.status NOT IN ('completed','archived') AND (?='' OR c.code=? COLLATE NOCASE)
            ORDER BY t.priority,COALESCE(t.due_on,'9999-12-31'),t.id LIMIT ?''',
            (view['filters']['course'],view['filters']['course'],LIMIT+1))
        if rows is None: return
        view['tasks'] = rows[:LIMIT]
        if len(rows)>LIMIT: view['limits'].append('Task inbox limited to 100; use the full task workspace for remaining items.')
        view['summary']['open_tasks'] = len(view['tasks'])
        view['summary']['overdue_tasks'] = sum(bool(r['due_on'] and r['due_on']<view['date']) for r in view['tasks'])

    def _effort(self, con, view, start):
        # Course-scoped attribution is safe for linked planner tasks and canonical study plan items.
        rows = self._read(con, view, 'effort', '''SELECT SUM(i.planned_minutes) planned_minutes,
            SUM(i.actual_minutes) actual_minutes,COUNT(i.actual_minutes) recorded_items,
            COUNT(*) total_items,SUM(CASE WHEN i.status='completed' THEN 1 ELSE 0 END) completed_items
            FROM daily_agenda_items i JOIN daily_agendas a ON a.id=i.agenda_id
            LEFT JOIN planner_tasks t ON i.source_type='planner_task' AND t.id=i.source_id
            LEFT JOIN study_plan_items sp ON i.source_type='study_plan_item' AND sp.id=i.source_id
            LEFT JOIN courses c ON c.id=COALESCE(t.course_id,sp.course_id)
            WHERE a.status IN ('approved','active','closed') AND a.agenda_date BETWEEN ? AND ?
            AND i.item_kind IN ('task','study','manual') AND (?='' OR c.code=? COLLATE NOCASE)''',
            (start,view['date'],view['filters']['course'],view['filters']['course']))
        if rows:
            row = rows[0]
            row['planned_minutes'] = row['planned_minutes'] or 0
            row['completed_items'] = row['completed_items'] or 0
            view['effort'] = row
        if view['filters']['course']:
            view['limits'].append('Course effort includes canonically linked planner tasks and dated study plan items; unlinked manual sessions remain excluded.')

    def _topics(self, con, view, lower, upper):
        session_ids = {r['id'] for r in view['assessments'] if r['category']=='evaluated'}
        if not session_ids:
            return
        rows = self._read(con, view, 'topic_observations', """SELECT s.id session_id,
            s.course_code_snapshot course_code,q.question_id,q.topic_id,t.name,t.deleted_at,
            c.code mapped_course,r.outcome,r.updated_at
            FROM assessment_response_evaluations r
            JOIN assessment_session_evaluations e ON e.id=r.session_evaluation_id
            JOIN assessment_test_sessions s ON s.id=e.session_id
            JOIN assessment_test_session_questions q ON q.id=r.session_question_id
            LEFT JOIN topics t ON t.id=q.topic_id LEFT JOIN courses c ON c.id=t.course_id
            WHERE julianday(r.updated_at) BETWEEN julianday(?) AND julianday(?)
            AND (?='' OR s.course_code_snapshot=? COLLATE NOCASE)
            ORDER BY julianday(r.updated_at) DESC,r.id LIMIT 501""",
            (lower,upper,view['filters']['course'],view['filters']['course']))
        if rows is None: return
        if len(rows)>500:
            view['limits'].append('Topic observations limited to 500 recent responses. Repeated question IDs count once; unknown equivalent questions cannot be deduplicated.')
        groups = {}
        for row in reversed(rows[:500]):
            if row['session_id'] not in session_ids: continue
            key = (row['course_code'],row['topic_id'])
            group = groups.setdefault(key, [])
            group.append(row)
        for (course, topic), group in sorted(groups.items(), key=lambda pair: str(pair[0])):
            last = group[-1]
            valid = bool(topic and last['name'] and not last['deleted_at'] and last['mapped_course']==course)
            latest = {}
            missed = set()
            recovered = set()
            for row in group:
                qid = row['question_id']
                if row['outcome']=='incorrect': missed.add(qid)
                if row['outcome']=='correct' and qid in missed: recovered.add(qid)
                latest[qid] = row['outcome']
            view['topics'].append({
                'id': topic or 'unmapped', 'name': last['name'] if valid else 'Mapping unavailable',
                'course_code': course, 'question_count': len(latest),
                'session_count': len({r['session_id'] for r in group}),
                'correct': sum(v=='correct' for v in latest.values()),
                'incorrect': sum(v=='incorrect' for v in latest.values()),
                'recovered': len(recovered), 'first_observed': group[0]['updated_at'],
                'last_observed': last['updated_at'], 'mapping_status': 'unreviewed' if valid else 'unavailable',
                'reason': 'Candidate for manual review; mapping and independence are not verified.' +
                    (' A correct retry followed a miss; independent recheck still needed.' if recovered else ''),
                'url': '/assessments/sessions/'+quote(last['session_id'],safe='')+'/evaluation',
            })
