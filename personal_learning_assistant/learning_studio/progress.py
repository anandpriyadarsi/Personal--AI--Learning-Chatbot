"""Append-only, ungraded reader state. Reads never initialize or migrate storage."""
import json
from .validation import identity, integer, require


class ProgressMixin:
    def reading_state(self, module_id, revision):
        self.module(module_id, revision)
        with self.store.connection() as con:
            if con.execute('PRAGMA user_version').fetchone()[0] == 1:
                return {'current': None, 'prior_revision': None, 'completed_sections':[]}
            current = con.execute('SELECT payload_json,timestamp FROM reading_events WHERE owner=? AND module_id=? AND revision=? ORDER BY seq DESC LIMIT 1',
                                  ('local-owner',module_id,revision)).fetchone()
            prior = con.execute('SELECT revision FROM reading_events WHERE owner=? AND module_id=? AND revision!=? ORDER BY seq DESC LIMIT 1',
                                ('local-owner',module_id,revision)).fetchone()
            completion = con.execute("SELECT payload_json FROM reading_events WHERE seq IN (SELECT max(seq) FROM reading_events WHERE owner=? AND module_id=? AND revision=? AND json_type(payload_json,'$.completed') IS NOT NULL GROUP BY json_extract(payload_json,'$.section_id'))",
                                     ('local-owner',module_id,revision)).fetchall()
            completed = [p['section_id'] for row in completion if (p:=json.loads(row['payload_json']))['completed']]
            return {'current': dict(json.loads(current['payload_json']), timestamp=current['timestamp']) if current else None,
                    'prior_revision': prior['revision'] if prior else None, 'completed_sections':completed}

    def engagement_state(self,module_id,revision,section_id):
        module=self.module(module_id,revision)
        require(any(s['id']==section_id for s in module['sections']),'Unknown lesson section.')
        with self.store.connection() as con:
            if con.execute('PRAGMA user_version').fetchone()[0]==1:return []
            rows=con.execute("SELECT payload_json FROM engagement_events WHERE seq IN (SELECT max(seq) FROM engagement_events WHERE owner=? AND module_id=? AND revision=? AND (json_extract(payload_json,'$.section_id')=? OR json_extract(payload_json,'$.block_scope')='revision') GROUP BY json_extract(payload_json,'$.block_index'),coalesce(json_extract(payload_json,'$.block_scope'),'section')) ORDER BY seq DESC LIMIT 120",
                             ('local-owner',module_id,revision,section_id)).fetchall()
            return [json.loads(row['payload_json']) for row in rows]

    def practice_state(self, module_id, revision):
        """Key-free exact-version counts. Reveals and self-reports have no input here."""
        module = self.module(module_id, revision)
        with self.store.connection() as con:
            rows = con.execute("""SELECT a.question_id,a.question_revision,a.correct,
                counts.attempt_count,counts.incorrect_count FROM attempts a JOIN
                (SELECT question_id,question_revision,max(seq) latest,count(*) attempt_count,
                 sum(CASE WHEN correct=0 THEN 1 ELSE 0 END) incorrect_count
                 FROM attempts WHERE owner=? AND module_id=? AND revision=?
                 GROUP BY question_id,question_revision) counts ON a.seq=counts.latest""",
                ('local-owner',module_id,revision)).fetchall()
        recorded={(r['question_id'],r['question_revision']):r for r in rows}
        result={}
        for question in module['questions']:
            row=recorded.get((question['id'],question['revision']))
            status='never_practised' if row is None else ('needs_review' if not row['correct'] else
                   'recovered_needs_recheck' if row['incorrect_count'] else 'checked_correct')
            result[question['id']]={'question_revision':question['revision'],'status':status,
                'attempt_count':row['attempt_count'] if row else 0,
                'incorrect_count':row['incorrect_count'] if row else 0}
        return result

    def _record_state(self, table, module_id, revision, payload):
        from .service import OWNER, canonical, now
        require(isinstance(payload, dict), 'Reader event must be an object.')
        identity(payload.get('event_id')); identity(payload.get('section_id'))
        module = self.module(module_id, revision)
        section = next((s for s in module['sections'] if s['id'] == payload['section_id']), None)
        require(section is not None, 'Unknown lesson section.')
        if table == 'reading_events':
            fields = {'event_id','section_id','view','completed','text_size','question_id','practice_mode','page','budget'}
            require(not payload.keys()-fields and 'view' in payload, 'Invalid reader event fields.')
            require(isinstance(payload['view'], str) and payload['view'] in {'learn','visualise','practice','revision','source'}, 'Invalid reading view.')
            if 'completed' in payload: require(type(payload['completed']) is bool, 'Completion is a user-reported boolean.')
            if 'page' in payload: integer(payload['page'],1,module['source']['page_count'])
            if 'budget' in payload: require(isinstance(payload['budget'],str) and payload['budget'] in {'5','15','full'},'Invalid revision budget.')
            if 'text_size' in payload: integer(payload['text_size'], 16, 28)
            if 'question_id' in payload:
                identity(payload['question_id'])
                require(any(q['id']==payload['question_id'] for q in module['questions']), 'Unknown question.')
            if 'practice_mode' in payload:
                require(isinstance(payload['practice_mode'],str) and payload['practice_mode'] in {'lesson','mixed','recheck'}, 'Invalid practice mode.')
        else:
            fields = {'event_id','section_id','block_index','response','action'}
            require(fields<=payload.keys() and not payload.keys()-fields-{'block_scope'}, 'Invalid engagement fields.')
            scope=payload.get('block_scope','section');require(scope in ('section','revision'),'Invalid engagement scope.')
            blocks=module['revision'] if scope=='revision' else section['blocks']
            integer(payload['block_index'],0,len(blocks)-1)
            block=blocks[payload['block_index']]
            require(block['kind'] in {'teaching','objectives','activity','recall'}, 'Block does not support engagement.')
            require(isinstance(payload['response'],str) and len(payload['response'])<=4000, 'Response exceeds limit.')
            require(isinstance(payload['action'],str) and payload['action'] in {'reflection','reveal','remembered'}, 'Unsupported engagement action.')
        encoded = canonical(payload)
        with self.store.connection(write=True) as con:
            old = con.execute('SELECT * FROM '+table+' WHERE event_id=?', (payload['event_id'],)).fetchone()
            if old:
                require((old['owner'],old['module_id'],old['revision'],old['payload_json'])==(OWNER,module_id,revision,encoded), 'Reader idempotency conflict.',409)
                return dict(payload,timestamp=old['timestamp'],ungraded=True)
            timestamp=now()
            con.execute('INSERT INTO '+table+'(event_id,owner,module_id,revision,payload_json,timestamp) VALUES(?,?,?,?,?,?)',
                        (payload['event_id'],OWNER,module_id,revision,encoded,timestamp))
        return dict(payload,timestamp=timestamp,ungraded=True)

    def record_progress(self, module_id, revision, payload):
        return self._record_state('reading_events',module_id,revision,payload)

    def record_engagement(self, module_id, revision, payload):
        return self._record_state('engagement_events',module_id,revision,payload)
