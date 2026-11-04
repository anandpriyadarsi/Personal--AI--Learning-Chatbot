"""Versioned, read-only canonical assessment feedback; never writes marks/mastery."""
import json
from .validation import validate_mapping,PackageError


def consent(studio,module_id,revision):
    with studio.store.connection() as con:
        if con is None or con.execute('PRAGMA user_version').fetchone()[0]==1:return False
        row=con.execute("SELECT payload_json FROM reading_events WHERE owner=? AND module_id=? AND revision=? AND json_type(payload_json,'$.assessment_feedback_consent') IS NOT NULL ORDER BY seq DESC LIMIT 1",('local-owner',module_id,revision)).fetchone()
    return bool(row and json.loads(row['payload_json'])['assessment_feedback_consent'])


def feedback(studio,package,report_loader):
    result={'schema':'anvaya.assessment-feedback.v1','consented':consent(studio,package['module_id'],package['module_revision']),
            'available':False,'needs_revision':False,'topics':[],'message':'Enable read-only assessment feedback to show source-linked revision suggestions.'}
    if not result['consented']:return result
    mapping=package['mapping']
    try:
        validate_mapping(mapping,studio.catalogue_loader())
        if not mapping or not mapping.get('topic_id'):raise PackageError('A reviewed stable topic identity is required.')
        report=report_loader(mapping['course_id'])
        if not report.get('available'):raise PackageError('Assessment feedback unavailable.')
        # Stable canonical topic IDs only. Names and reading completion never match scores.
        topics=[t for t in report.get('topics',[]) if t.get('topic_id')==mapping['topic_id']]
        result.update(available=True,message='Confirmed canonical assessment evidence only; reading completion is separate.')
        for topic in topics:
            score=topic.get('performance_percent')
            count=topic.get('question_count',0)
            if not isinstance(score,(int,float)) or not count:continue
            result['topics'].append({'topic_id':mapping['topic_id'],'name':mapping['topic_name'],
                'performance_percent':score,'question_count':count})
            if score<60:result['needs_revision']=True
        if not result['topics']:result['message']='No confirmed assessment result matches this exact topic yet.'
    except (PackageError,ValueError,RuntimeError,OSError):
        result['message']='Assessment evidence is unavailable or needs mapping review. Existing scores are unchanged.'
    return result
