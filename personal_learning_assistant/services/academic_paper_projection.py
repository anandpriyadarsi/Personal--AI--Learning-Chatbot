"""Read only, allowlisted projection of immutable student-entered paper reviews.

A draft amendment does not erase the last submitted revision. Eligibility is
as-of the injected clock; these marks never establish evaluated performance.
"""
import json
import re
from datetime import datetime
from urllib.parse import quote

MAX_PAYLOAD_BYTES = 262144
MAX_QUESTIONS = 200


def paper_rows(con, *, lower, upper, course, limit):
    rows = [dict(r) for r in con.execute('''
        WITH bounded AS (
            SELECT session_id,revision,status,provenance,
                CASE WHEN length(CAST(snapshot_json AS BLOB))<=? AND json_valid(snapshot_json)
                     THEN snapshot_json ELSE '{}' END payload
            FROM assessment_extended_self_reviews WHERE status='submitted'
        ), eligible AS (
            SELECT b.*,json_extract(payload,'$.submitted_at') review_at,
                ROW_NUMBER() OVER (PARTITION BY b.session_id ORDER BY b.revision DESC) rank
            FROM bounded b JOIN assessment_test_sessions s ON s.id=b.session_id
            WHERE json_type(payload,'$.submitted_at')='text'
              AND julianday(json_extract(payload,'$.submitted_at')) BETWEEN julianday(?) AND julianday(?)
              AND julianday(s.started_at)<=julianday(json_extract(payload,'$.submitted_at'))
              AND (?='' OR s.course_code_snapshot=? COLLATE NOCASE)
        )
        SELECT e.*,s.title_snapshot title,s.course_code_snapshot course_code,
            s.status session_status,s.mode,s.question_count,s.max_marks_milli,
            json_extract(CASE WHEN length(CAST(x.metadata_json AS BLOB))<=? AND json_valid(x.metadata_json)
                THEN x.metadata_json ELSE '{}' END, '$.package_identity.snapshot_sha256') source_hash
        FROM eligible e JOIN assessment_test_sessions s ON s.id=e.session_id
        JOIN assessment_extended_execution x ON x.session_id=e.session_id
        WHERE rank=1 ORDER BY julianday(review_at) DESC,session_id LIMIT ?
        ''', (MAX_PAYLOAD_BYTES, lower, upper, course, course, MAX_PAYLOAD_BYTES, limit+1))]
    if not rows:
        return [], False
    ids = [r['session_id'] for r in rows]
    questions = {}
    # One bounded batch; no question content or solutions leave their owner.
    qrows = con.execute('SELECT session_id,id,max_marks_milli FROM assessment_test_session_questions '
        'WHERE session_id IN ('+','.join('?' for _ in ids)+') ORDER BY session_id,id LIMIT ?',
        (*ids, (limit+1)*MAX_QUESTIONS+1)).fetchall()
    if len(qrows)>(limit+1)*MAX_QUESTIONS:
        return [], True
    for q in qrows:
        questions.setdefault(q['session_id'], {})[q['id']] = q['max_marks_milli']
    result = []
    for row in rows:
        try:
            snapshot = json.loads(row['payload'])
            at = datetime.fromisoformat(row['review_at'].replace('Z', '+00:00'))
            if at.tzinfo is None:
                continue
            identity = snapshot.get('package_identity', {})
            if (identity.get('authority')!='user_private_self_check'
                or not re.fullmatch(r'[0-9a-f]{64}', str(row['source_hash']))
                or identity.get('snapshot_sha256')!=row['source_hash']):
                continue
            items = snapshot['items']
            expected = questions.get(row['session_id'], {})
            if (snapshot.get('status')!='submitted' or snapshot.get('revision')!=row['revision']
                or snapshot.get('provenance')!='self_assessed' or row['provenance']!='self_assessed'
                or not isinstance(items, dict) or not 0<len(expected)<=MAX_QUESTIONS
                or len(expected)!=row['question_count'] or set(items)!=set(expected)
                or sum(expected.values())!=row['max_marks_milli']):
                continue
            marks = []
            for qid, item in items.items():
                mark = item['awarded_marks_milli']
                if type(mark) is not int or not 0<=mark<=expected[qid]:
                    raise ValueError('Invalid marks')
                marks.append(mark)
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            continue
        sid = row['session_id']
        result.append({'id':sid, 'title':row['title'], 'course_code':row['course_code'],
            'status':row['session_status'], 'mode':row['mode'], 'date':row['review_at'],
            'earned':sum(marks)/1000, 'max_marks':row['max_marks_milli']/1000,
            'question_count':row['question_count'], 'category':'self_reported',
            'independence':'unknown', 'mapping_review':'not_established',
            'review_revision':row['revision'],
            'package_snapshot_sha256':row['source_hash'],
            'source_refs':[sid, sid+':self-review:'+str(row['revision'])],
            'url':'/assessments/sessions/'+quote(sid,safe='')})
    return result, len(rows)>limit
