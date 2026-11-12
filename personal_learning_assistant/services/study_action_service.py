"""Deterministic reviewed suggestions with server-owned, exact destinations.

No task is created here. Existing source preview/intent owners retain validation,
provider consent and idempotent task creation.
"""
from urllib.parse import quote


def suggest_actions(context, max_actions=3):
    cap = min(3, max(0, int(max_actions)))
    date = context.get('date', '')
    actions = []
    for task in sorted(context.get('tasks', []), key=lambda t: (t.get('due_on') or '9999',t['id'])):
        if not task.get('due_on') or task['due_on'] >= date:
            continue
        actions.append(dict(kind='overdue_commitment', title=task['title'],
            reason='Your open commitment was due '+task['due_on']+'. Review its timing before replanning.',
            source_refs=['planner_task:'+task['id']], evidence_date=task['due_on'],
            url='/planning/tasks?status=all#task-'+quote(task['id'],safe=''), label='Review commitment'))
    for topic in context.get('topics', []):
        if topic.get('mapping_status') != 'confirmed' or not topic.get('incorrect'):
            continue
        actions.append(dict(kind='qualified_recheck',title=topic['name'],
            reason='Inspect the qualified outcome before choosing a recheck; mastery remains unknown.',
            source_refs=topic.get('source_refs',[]),evidence_date=topic.get('last_observed'),
            url=topic['url'],label='Inspect evidence'))
    for source in context.get('revision_queue', []):
        if (source.get('mapping_status') != 'confirmed' or not source.get('current') or
                not date or not source.get('next_review_on') or source['next_review_on'] > date):
            continue
        module_id,revision = source.get('module_id'),source.get('revision')
        if not module_id or type(revision) is not int or revision < 1:
            continue
        actions.append(dict(kind='explicit_revision',title=source['title'],
            reason='Your explicitly scheduled source revision is due '+source['next_review_on']+'.',
            source_refs=source.get('source_refs',[]),evidence_date=source['next_review_on'],
            url='/academic-evidence/learning/'+quote(module_id,safe='')+'/'+str(revision)+'/study-preview',
            label='Preview study task'))
    return actions[:cap]
