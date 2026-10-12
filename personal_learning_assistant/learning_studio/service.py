"""Thin domain orchestration. No Tutor, official grades, Notes or mastery writes."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
from .store import StudioStore
from .validation import PackageError, identity, integer, require, validate_mapping, validate_package

OWNER = 'local-owner'  # Existing ANVAYA is a single-owner local app, not multiuser auth.


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class LearningStudioService:
    def __init__(self, path, *, source_loader, catalogue_loader):
        self.store = StudioStore(path)
        self.source_loader = source_loader
        self.catalogue_loader = catalogue_loader

    def stage(self, package, assets=None):
        require(isinstance(package, dict) and isinstance(package.get('source'), dict), 'Missing source/package.')
        raw = self.source_loader(package['source'].get('source_id'))
        p = validate_package(package, self.catalogue_loader(), raw, assets)
        encoded = canonical(p)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.store.connection(write=True) as con:
            existing = con.execute('SELECT digest FROM modules WHERE module_id=? AND revision=?',
                                   (p['module_id'], p['module_revision'])).fetchone()
            if existing:
                require(existing['digest'] == digest, 'A module revision is immutable. Increment its revision.', 409)
                existing_assets = {r['name']: r['bytes'] for r in con.execute(
                    'SELECT name,bytes FROM assets WHERE module_id=? AND revision=?', (p['module_id'], p['module_revision']))}
                require(existing_assets == (assets or {}), 'Assets for this revision are immutable.', 409)
            else:
                # A changed question must receive a newer stable question revision.
                history = con.execute('SELECT package_json FROM modules WHERE module_id=? ORDER BY revision DESC', (p['module_id'],)).fetchall()
                if history:
                    latest = json.loads(history[0]['package_json'])
                    require(p['module_revision'] > latest['module_revision'], 'New module revisions must increase.', 409)
                    historical_questions = {}
                    for row in history:
                        for old_q in json.loads(row['package_json'])['questions']:
                            historical_questions.setdefault(old_q['id'], old_q)
                    for q in p['questions']:
                        old_q = historical_questions.get(q['id'])
                        if old_q:
                            require(q['revision'] >= old_q['revision'] and
                                    (q == old_q or q['revision'] > old_q['revision']),
                                    'Changed questions require a new question revision, including removed questions.', 409)
                mapping = p['mapping'] or {}
                con.execute('INSERT INTO modules VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (p['module_id'], p['module_revision'], digest, p['title'], p['unit'],
                     mapping.get('course_id'), mapping.get('topic_name'), encoded, raw, now()))
                for name, asset in (assets or {}).items():
                    con.execute('INSERT INTO assets VALUES(?,?,?,?)', (p['module_id'], p['module_revision'], name, asset))
        return {'module_id': p['module_id'], 'revision': p['module_revision'], 'state': 'staged',
                'semantic_review_pages': sum(page['status'] != 'verified' for page in p['pages'])}

    def _row(self, con, module_id, revision, *, staged=False):
        identity(module_id); integer(revision, 1, 1000000)
        require(con is not None, 'Module not found.', 404)
        row = con.execute('SELECT m.* FROM modules m WHERE m.module_id=? AND m.revision=?' +
            ('' if staged else ' AND EXISTS(SELECT 1 FROM publications p WHERE p.module_id=m.module_id AND p.revision=m.revision)'),
            (module_id, revision)).fetchone()
        require(row is not None, 'Module not found.', 404)
        p = json.loads(row['package_json'])
        require(hashlib.sha256(canonical(p).encode()).hexdigest() == row['digest'], 'Module integrity failure.', 409)
        return row, p

    def publish(self, module_id, revision):
        self.module(module_id, revision, staged=True)
        with self.store.connection(write=True) as con:
            row, p = self._row(con, module_id, revision, staged=True)
            assets = {a['name']: a['bytes'] for a in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?', (module_id, revision))}
            # Re-resolve registry and catalogue after staging; no trusting an obsolete preview.
            try:
                raw = self.source_loader(p['source']['source_id'])
            except PackageError: raise
            except Exception as error:
                raise PackageError('Registered source is unavailable; the staged revision was not published.', 503) from error
            validate_package(p, self.catalogue_loader(), raw, assets)
            require(raw == row['source_blob'], 'Staged source snapshot no longer matches its registry source.', 409)
            con.execute('INSERT OR IGNORE INTO publications VALUES(?,?,?)', (module_id, revision, now()))
            active = con.execute('SELECT revision FROM active_modules WHERE module_id=?', (module_id,)).fetchone()
            require(not active or active['revision'] <= revision, 'Cannot roll back active module silently.', 409)
            con.execute('INSERT INTO active_modules VALUES(?,?) ON CONFLICT(module_id) DO UPDATE SET revision=excluded.revision', (module_id, revision))
        return {'module_id': module_id, 'revision': revision, 'state': 'published'}

    def module(self, module_id, revision, *, staged=False, public=True):
        with self.store.connection() as con:
            _, p = self._row(con, module_id, revision, staged=staged)
            p = copy.deepcopy(p)
            p['history'] = [r['revision'] for r in con.execute(
                'SELECT revision FROM publications WHERE module_id=? ORDER BY revision DESC', (module_id,))]
        if public:
            for q in p['questions']:
                q.pop('correct_index'); q.pop('explanation')
        return p

    def source(self, module_id, revision, *, staged=False):
        with self.store.connection() as con:
            row, p = self._row(con, module_id, revision, staged=staged)
            raw = row['source_blob']
            require(hashlib.sha256(raw).hexdigest() == p['source']['sha256'], 'Source snapshot integrity failure.', 409)
            return raw

    def asset(self, module_id, revision, name, *, staged=False):
        with self.store.connection() as con:
            self._row(con, module_id, revision, staged=staged)
            row = con.execute('SELECT bytes FROM assets WHERE module_id=? AND revision=? AND name=?', (module_id, revision, name)).fetchone()
            require(row is not None, 'Asset not owned by this module revision.', 404)
            return row['bytes']

    def library(self, *, course_id=None, search='', topic='', offset=0, limit=12):
        integer(offset, 0, 1000000); integer(limit, 1, 50)
        require(isinstance(search, str) and len(search) <= 200, 'Search exceeds 200 characters.')
        cat = self.catalogue_loader()
        courses = copy.deepcopy(cat.get('courses', []))
        counts = {}
        result = {'courses': courses, 'available': cat.get('available', False), 'modules': [], 'total': 0,
                  'unmapped_count': 0, 'staged': [], 'offset': offset, 'limit': limit}
        with self.store.connection() as con:
            if con is not None:
                counts = {r['course_id']: r['n'] for r in con.execute('SELECT m.course_id,count(*) n FROM modules m JOIN active_modules a USING(module_id,revision) GROUP BY m.course_id')}
                result['unmapped_count'] = counts.get(None, 0)
                result['staged'] = [dict(r) for r in con.execute('SELECT module_id,revision,title FROM modules m WHERE NOT EXISTS(SELECT 1 FROM publications p WHERE p.module_id=m.module_id AND p.revision=m.revision) ORDER BY created_at DESC LIMIT 20')]
                if course_id is not None:
                    require(course_id == 'unmapped' or any(c['id'] == course_id for c in courses), 'Course not registered.', 404)
                    clauses = ['m.course_id IS NULL'] if course_id == 'unmapped' else ['m.course_id=?']
                    params = [] if course_id == 'unmapped' else [course_id]
                    if search:
                        # Casefold in Python happens only for bounded metadata, never full package bodies.
                        clauses.append("m.title LIKE ? ESCAPE '\\'")
                        params.append('%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
                    if topic:
                        clauses.append('m.topic_name=?'); params.append(topic)
                    query = ' FROM modules m JOIN active_modules a USING(module_id,revision) WHERE ' + ' AND '.join(clauses)
                    result['total'] = con.execute('SELECT count(*)' + query, params).fetchone()[0]
                    result['modules'] = [dict(r) for r in con.execute('SELECT m.module_id,m.revision,m.title,m.unit,m.topic_name,m.created_at' + query + ' ORDER BY m.unit,m.topic_name,m.title,m.module_id LIMIT ? OFFSET ?', (*params, limit, offset))]
                else:
                    result['modules'] = []
            for course in courses:
                course['module_count'] = counts.get(course['id'], 0)
                course['academic_year'] = course.get('academic_year') or 'Academic year unspecified'
        return result

    def attempt(self, module_id, payload):
        require(isinstance(payload, dict), 'Attempt payload must be an object.')
        required = {'event_id', 'module_revision', 'source_sha256', 'question_id', 'question_revision', 'selection'}
        require(required <= payload.keys() and not payload.keys() - required - {'is_correct'}, 'Invalid attempt fields; identity and mapping are server owned.')
        identity(payload['event_id']); identity(payload['question_id'])
        integer(payload['module_revision'], 1, 1000000); integer(payload['question_revision'], 1, 1000000)
        self.module(module_id, payload['module_revision'])
        with self.store.connection(write=True) as con:
            _, p = self._row(con, module_id, payload['module_revision'])
            require(p['source']['sha256'] == payload['source_sha256'], 'Stale source version.', 409)
            q = next((q for q in p['questions'] if q['id'] == payload['question_id']), None)
            require(q is not None and q['revision'] == payload['question_revision'], 'Unknown question version.', 409)
            integer(payload['selection'], 0, len(q['options']) - 1)
            context = (OWNER, module_id, p['module_revision'], p['source']['sha256'], q['id'], q['revision'], payload['selection'])
            old = con.execute('SELECT * FROM attempts WHERE event_id=?', (payload['event_id'],)).fetchone()
            if old:
                require(tuple(old[key] for key in ('owner', 'module_id', 'revision', 'source_hash', 'question_id', 'question_revision', 'selection')) == context, 'Idempotency key conflict.', 409)
                return self._feedback(old, q)
            number = con.execute('SELECT count(*) FROM attempts WHERE owner=? AND module_id=? AND revision=? AND question_id=? AND question_revision=?', (OWNER, module_id, p['module_revision'], q['id'], q['revision'])).fetchone()[0] + 1
            con.execute('INSERT INTO attempts(event_id,owner,module_id,revision,source_hash,question_id,question_revision,selection,correct,attempt_number,timestamp) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (payload['event_id'], *context, int(payload['selection'] == q['correct_index']), number, now()))
            row = con.execute('SELECT * FROM attempts WHERE event_id=?', (payload['event_id'],)).fetchone()
            return self._feedback(row, q)

    @staticmethod
    def _feedback(row, question):
        return {'event_id': row['event_id'], 'correct': bool(row['correct']), 'selection': row['selection'],
                'attempt_number': row['attempt_number'], 'timestamp': row['timestamp'],
                'correct_index': question['correct_index'], 'explanation': question['explanation']}

    def weak(self, module_id, revision):
        with self.store.connection() as con:
            _, p = self._row(con, module_id, revision)
            rows = con.execute('SELECT * FROM attempts WHERE owner=? AND module_id=? AND revision=? ORDER BY seq', (OWNER, module_id, revision)).fetchall()
            result = []
            for q in p['questions']:
                attempts = [r for r in rows if r['question_id'] == q['id'] and r['question_revision'] == q['revision']]
                wrong = [r for r in attempts if not r['correct']]
                if wrong:
                    latest = attempts[-1]
                    result.append({'question_id': q['id'], 'prompt': q['prompt'], 'pages': q['pages'],
                        'incorrect_count': len(wrong), 'last_incorrect': wrong[-1]['timestamp'],
                        'latest_selection': latest['selection'], 'latest_response': q['options'][latest['selection']],
                        'latest_correct': bool(latest['correct']), 'attempt_count': len(attempts),
                        'status': 'recovered_needs_recheck' if latest['correct'] else 'needs_review'})
            return result

    def evidence(self):
        summary = {'schema': 'anvaya.learning-evidence-summary.v1', 'authority': 'low-stakes-practice',
                   'attempts': 0, 'ever_missed': 0, 'latest_correct': 0, 'reviewed_attempts': 0,
                   'unmapped_attempts': 0, 'groups': [], 'trend': [], 'evidence_label': 'No evidence',
                   'tutor_available': False, 'tutor_reason': 'Existing Tutor entry point does not consume this versioned evidence contract.'}
        with self.store.connection() as con:
            if con is None: return summary
            rows = con.execute('SELECT a.*,m.course_id,m.topic_name FROM attempts a JOIN modules m USING(module_id,revision) WHERE owner=? ORDER BY seq', (OWNER,)).fetchall()
            grouped = {}
            trend = {}
            questions = {}
            for r in rows:
                day = r['timestamp'][:10]
                daily = trend.setdefault(day, {'day': day, 'attempts': 0, 'incorrect': 0})
                daily['attempts'] += 1; daily['incorrect'] += not r['correct']
                key = (r['course_id'], r['topic_name'])
                group = grouped.setdefault(key, {'course_id': key[0], 'topic_name': key[1], 'attempts': 0, 'incorrect': 0})
                group['attempts'] += 1; group['incorrect'] += not r['correct']
                qkey = (r['module_id'], r['revision'], r['question_id'], r['question_revision'])
                question = questions.setdefault(qkey, {'ever_wrong': False, 'latest_correct': False})
                question['ever_wrong'] |= not r['correct']; question['latest_correct'] = bool(r['correct'])
            summary.update(attempts=len(rows), groups=list(grouped.values()), trend=list(trend.values()),
                ever_missed=sum(q['ever_wrong'] for q in questions.values()),
                latest_correct=sum(q['latest_correct'] for q in questions.values()),
                reviewed_attempts=sum(r['course_id'] is not None for r in rows),
                unmapped_attempts=sum(r['course_id'] is None for r in rows),
                evidence_label='Limited evidence' if len(questions) < 5 else 'Low-stakes practice evidence')
            return summary

    def export(self):
        with self.store.connection() as con:
            rows = [] if con is None else [dict(r) for r in con.execute('SELECT event_id,module_id,revision,source_hash,question_id,question_revision,selection,correct,attempt_number,timestamp FROM attempts WHERE owner=? ORDER BY seq', (OWNER,))]
        return {'schema': 'anvaya.learning-evidence-export.v1', 'owner_scope': OWNER, 'events': rows}
