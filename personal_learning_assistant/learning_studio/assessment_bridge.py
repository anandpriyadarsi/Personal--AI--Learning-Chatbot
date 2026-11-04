"""Versioned, read-only canonical assessment feedback; never writes marks/mastery."""
import json
from .validation import validate_mapping,PackageError


def consent(studio,module_id,revision):
    with studio.store.connection() as con:
        if con is None or con.execute('PRAGMA user_version').fetchone()[0]==1:return False
        row=con.execute("SELECT payload_json FROM reading_events WHERE owner=? AND module_id=? AND revision=? AND json_type(payload_json,'$.assessment_feedback_consent') IS NOT NULL ORDER BY seq DESC LIMIT 1",('local-owner',module_id,revision)).fetchone()
    return bool(row and json.loads(row['payload_json'])['assessment_feedback_consent'])


def feedback(studio,package,report_loader,*,assessment_mapping=None):
    result={'schema':'anvaya.assessment-feedback.v1','consented':consent(studio,package['module_id'],package['module_revision']),
            'available':False,'needs_revision':False,'topics':[],'message':'Enable read-only assessment feedback to show source-linked revision suggestions.'}
    if not result['consented']:return result
    mapping=package['mapping']
    try:
        validate_mapping(mapping,studio.catalogue_loader())
        if not mapping or not mapping.get('topic_id'):raise PackageError('A reviewed stable topic identity is required.')
        selected=assessment_mapping or mapping
        report=report_loader(selected['course_id'])
        if not report.get('available'):raise PackageError('Assessment feedback unavailable.')
        # Stable canonical topic IDs only. Names and reading completion never match scores.
        topics=[t for t in report.get('topics',[]) if t.get('topic_id')==selected['topic_id']]
        result.update(available=True,message='Confirmed canonical assessment evidence only; reading completion is separate.')
        for topic in topics:
            score=topic.get('performance_percent')
            count=topic.get('question_count',0)
            if not isinstance(score,(int,float)) or not count:continue
            result['topics'].append({'topic_id':selected['topic_id'],'name':topic.get('label',mapping['topic_name']),
                'performance_percent':score,'question_count':count})
            if score<60:result['needs_revision']=True
        if not result['topics']:result['message']='No confirmed assessment result matches this exact topic yet.'
    except (PackageError,ValueError,RuntimeError,OSError):
        result['message']='Assessment evidence is unavailable or needs mapping review. Existing scores are unchanged.'
    return result


def reviewed_link(studio,module_id,revision):
    with studio.store.connection() as con:
        if con is None:return None
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='module_assessment_links'").fetchone():return None
        row=con.execute('SELECT course_id,topic_id FROM module_assessment_links WHERE owner=? AND module_id=? AND revision=? ORDER BY seq DESC LIMIT 1',('local-owner',module_id,revision)).fetchone()
        return dict(row) if row else None


def save_reviewed_link(studio,module_id,revision,course_id,topic_id):
    from .service import now
    studio.module(module_id,revision)
    with studio.store.connection(write=True) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS module_assessment_links(
          seq INTEGER PRIMARY KEY,owner TEXT NOT NULL,module_id TEXT NOT NULL,
          revision INTEGER NOT NULL,course_id TEXT NOT NULL,topic_id TEXT NOT NULL,reviewed_at TEXT NOT NULL,
          FOREIGN KEY(module_id,revision) REFERENCES publications(module_id,revision))''')
        old=con.execute('SELECT course_id,topic_id FROM module_assessment_links WHERE owner=? AND module_id=? AND revision=? ORDER BY seq DESC LIMIT 1',('local-owner',module_id,revision)).fetchone()
        if old and old['course_id']==course_id and old['topic_id']==topic_id:return
        con.execute('INSERT INTO module_assessment_links(owner,module_id,revision,course_id,topic_id,reviewed_at) VALUES(?,?,?,?,?,?)',('local-owner',module_id,revision,course_id,topic_id,now()))


def formal_states(database_path,course_id):
    """Bounded canonical schedule/attempt metadata, separate from reading state."""
    from contextlib import closing
    from pathlib import Path
    import sqlite3
    path=Path(database_path).absolute()
    if not path.is_file() or any(p.is_symlink() for p in (path,*path.parents)):return []
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
        con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
        rows=con.execute('''SELECT a.id,a.title,a.due_on,
          EXISTS(SELECT 1 FROM assessment_test_sessions s WHERE s.assessment_id=a.id AND s.status IN ('submitted','timed_out')) completed
          FROM assessments a WHERE a.course_id=? AND a.deleted_at IS NULL
          AND EXISTS(SELECT 1 FROM assessment_runtime_specs r WHERE r.assessment_id=a.id)
          ORDER BY a.updated_at DESC,a.id LIMIT 10''',(course_id,)).fetchall()
    return [{'id':r['id'],'title':r['title'],'state':('Completed formal attempt' if r['completed'] else 'Scheduled: '+r['due_on'] if r['due_on'] else 'Available in Assessment Studio'),
             'history':bool(r['completed'])} for r in rows]
