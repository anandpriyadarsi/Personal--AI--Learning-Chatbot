"""Thin domain orchestration. No Tutor, official grades, Notes or mastery writes."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
from .store import StudioStore
from .progress import ProgressMixin
from .review_store import ReviewStoreMixin
from .mapping_review import MappingReviewMixin
from .candidates import CandidateMixin
from .validation import PackageError, identity, integer, require, validate_mapping, validate_package

OWNER = 'local-owner'  # Existing ANVAYA is a single-owner local app, not multiuser auth.


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class LearningStudioService(ProgressMixin, ReviewStoreMixin, MappingReviewMixin, CandidateMixin):
    def __init__(self, path, *, source_loader, catalogue_loader):
        self.store = StudioStore(path)
        self.source_loader = source_loader
        self.catalogue_loader = catalogue_loader

    def stage(self, package, assets=None, coverage=None, *, candidate=False):
        require(isinstance(package, dict) and isinstance(package.get('source'), dict), 'Missing source/package.')
        raw = self.source_loader(package['source'].get('source_id'))
        p = validate_package(package, self.catalogue_loader(), raw, assets)
        if coverage is not None:
            from .coverage import validate_coverage
            validate_coverage(coverage, p, raw, assets)
        encoded = canonical(p)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.store.connection(write=True) as con:
            existing = con.execute('SELECT digest FROM modules WHERE module_id=? AND revision=?',
                                   (p['module_id'], p['module_revision'])).fetchone()
            if existing:
                if candidate:
                    require(not con.execute('SELECT 1 FROM publications WHERE module_id=? AND revision=?',
                        (p['module_id'],p['module_revision'])).fetchone(),'Candidate target was published; reload before creating a new revision.',409)
                    prior=con.execute('SELECT record_json FROM coverage_reports WHERE module_id=? AND revision=? ORDER BY seq DESC LIMIT 1',
                        (p['module_id'],p['module_revision'])).fetchone()
                    saved=json.loads(prior['record_json']) if prior else None
                    if coverage is not None and saved is not None:
                        coverage=copy.deepcopy(coverage);coverage['review']['reviewed_at']=saved['review']['reviewed_at']
                    require(saved==coverage,'Candidate correction rationale conflicts; reload before creating another revision.',409)
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
            if coverage is not None:
                from .coverage import digest as coverage_digest
                con.execute('INSERT OR IGNORE INTO coverage_reports(module_id,revision,digest,record_json,timestamp) VALUES(?,?,?,?,?)',
                    (p['module_id'],p['module_revision'],coverage_digest(coverage),canonical(coverage),now()))
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
                  'unmapped_count': 0, 'unavailable_count': 0, 'staged': [], 'offset': offset, 'limit': limit}
        with self.store.connection() as con:
            if con is not None:
                counts = {r['course_id']: r['n'] for r in con.execute('SELECT m.course_id,count(*) n FROM modules m JOIN active_modules a USING(module_id,revision) GROUP BY m.course_id')}
                result['unmapped_count'] = counts.get(None, 0)
                current_ids = {c['id'] for c in courses}
                result['unavailable_count'] = sum(n for key,n in counts.items() if key is not None and key not in current_ids)
                result['staged'] = [dict(r) for r in con.execute('SELECT module_id,revision,title FROM modules m WHERE NOT EXISTS(SELECT 1 FROM publications p WHERE p.module_id=m.module_id AND p.revision=m.revision) ORDER BY created_at DESC LIMIT 20')]
                if course_id is not None:
                    require(course_id in {'unmapped', 'unavailable'} or any(c['id'] == course_id for c in courses), 'Course not registered.', 404)
                    if course_id == 'unmapped':
                        clauses, params = ['m.course_id IS NULL'], []
                    elif course_id == 'unavailable':
                        ids = sorted(current_ids)
                        clauses = ['m.course_id IS NOT NULL']
                        params = ids
                        if ids: clauses.append('m.course_id NOT IN (' + ','.join('?' for _ in ids) + ')')
                    else:
                        clauses, params = ['m.course_id=?'], [course_id]
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
                course['semester'] = course.get('semester') or 'Semester unspecified'
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
                    related = next((section['id'] for section in p['sections'] if
                        set(q['pages']) & (set(section['pages']) | {page for block in section['blocks'] for page in block['pages']})), None)
                    result.append({'question_id': q['id'], 'prompt': q['prompt'], 'pages': q['pages'],
                        'lesson_section_id': related, 'source_page': q['pages'][0],
                        'incorrect_count': len(wrong), 'last_incorrect': wrong[-1]['timestamp'],
                        'latest_selection': latest['selection'], 'latest_response': q['options'][latest['selection']],
                        'latest_correct': bool(latest['correct']), 'attempt_count': len(attempts),
                        'status': 'recovered_needs_recheck' if latest['correct'] else 'needs_review'})
            return result

    def evidence(self):
        from .evidence import summarize
        return summarize(self)

    def export(self):
        with self.store.connection() as con:
            rows = [] if con is None else [dict(r) for r in con.execute('SELECT event_id,module_id,revision,source_hash,question_id,question_revision,selection,correct,attempt_number,timestamp FROM attempts WHERE owner=? ORDER BY seq', (OWNER,))]
        return {'schema': 'anvaya.learning-evidence-export.v1', 'owner_scope': OWNER, 'events': rows}

    def review_context(self, module_id, revision):
        """Read-only, module/version-scoped handoff from already-graded events."""
        p = self.module(module_id, revision)
        self.source(module_id, revision)  # Verify the immutable source snapshot.
        with self.store.connection() as con:
            rows = con.execute('SELECT question_id,question_revision FROM attempts WHERE owner=? AND module_id=? AND revision=?',
                               (OWNER,module_id,revision)).fetchall()
        mapping_status = 'unmapped'
        if p['mapping']:
            try:
                validate_mapping(p['mapping'],self.catalogue_loader())
                mapping_status = 'reviewed_current_catalogue'
            except PackageError:
                mapping_status = 'needs_review'
        questions = {q['id']:q for q in p['questions']}
        missed = []
        for item in self.weak(module_id,revision):
            q = questions[item['question_id']]
            lesson = item['lesson_section_id']
            base = f'/learning/modules/{module_id}/{revision}'
            missed.append({**item,'question_revision':q['revision'],
                'lesson_url':base+('?view=learn#'+lesson if lesson else '?view=source#source-page-'+str(item['source_page'])),
                'source_urls':[base+'?view=source#source-page-'+str(page) for page in item['pages']],
                'question_url':base+'?view=practice#question-'+q['id']})
        distinct = len({(r['question_id'],r['question_revision']) for r in rows})
        return {'schema':'anvaya.learning-review-context.v1','authority':'low-stakes-practice',
                'module_id':module_id,'module_revision':revision,'title':p['title'],
                'source':p['source'],'mapping_snapshot':p['mapping'],'mapping_status':mapping_status,
                'semantic_review_pages':sum(page['status']!='verified' for page in p['pages']),
                'attempts':len(rows),'evidence_label':'No evidence' if not rows else ('Limited evidence' if distinct<5 else 'Low-stakes practice evidence'),
                'missed_questions':missed,'automatic_tutor_consumption':False}
