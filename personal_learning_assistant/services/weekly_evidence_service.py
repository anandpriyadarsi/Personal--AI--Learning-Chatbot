"""Pure SQLite read adapter shared by weekly review and owner-authorized Analysis."""
from datetime import datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
from personal_learning_assistant.domain.weekly_evidence import Metric, POLICY_VERSION


def instant(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fingerprint(evidence):
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k,v in value.items() if k != 'as_of'}
        if isinstance(value, (list, tuple)):
            return [stable(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(stable(evidence), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def aggregate_connection(con, start, end, *, as_of=None, course_id='', local_timezone='Asia/Kolkata'):
    now = instant(as_of) if as_of else datetime.now(timezone.utc)
    if now is None:
        raise ValueError('Evidence clock must be an ISO instant.')
    zone = ZoneInfo(local_timezone)
    scope = dict(start=start, end=end, timezone=local_timezone, course_id=course_id)
    stamp = now.isoformat()
    rows = [dict(r) for r in con.execute('''SELECT i.*,a.agenda_date,a.approved_at
        FROM daily_agenda_items i JOIN daily_agendas a ON a.id=i.agenda_id
        LEFT JOIN planner_tasks t ON i.source_type='planner_task' AND t.id=i.source_id
        LEFT JOIN study_plan_items s ON i.source_type='study_plan_item' AND s.id=i.source_id
        WHERE a.agenda_date BETWEEN ? AND ? AND i.item_kind IN ('task','study','manual')
        AND (?='' OR COALESCE(t.course_id,s.course_id)=?)''',(start,end,course_id,course_id))]
    eligible = [r for r in rows if instant(r['approved_at']) and instant(r['starts_at']) and
                instant(r['ends_at']) and instant(r['ends_at']) > instant(r['starts_at']) and
                not (r['status'] in ('moved','skipped') and r['reason'] and
                     instant(r['updated_at']) and instant(r['updated_at']) < instant(r['starts_at']))]
    logs = []
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'planner_work_logs' in tables:
        logs = [dict(r) for r in con.execute('''SELECT l.* FROM planner_work_logs l
            LEFT JOIN planner_tasks t ON t.id=l.task_id
            WHERE (?='' OR t.course_id=?)''',(course_id,course_id))]
    observed_logs = [r for r in logs if instant(r['occurred_at']) and instant(r['occurred_at']) <= now]
    superseded = {r['supersedes_id'] for r in observed_logs if r.get('supersedes_id')}
    active_logs = [r for r in observed_logs if r['id'] not in superseded]
    # Any corresponding receipt identifies a derived agenda projection, including future receipts.
    logged_origins = {r['agenda_item_id'] for r in logs if r.get('agenda_item_id')}
    period_logs = [r for r in active_logs if instant(r['occurred_at']) and
                   start <= instant(r['occurred_at']).astimezone(zone).date().isoformat() <= end and
                   instant(r['occurred_at']) <= now]
    legacy = [r for r in eligible if r['id'] not in logged_origins and r['actual_minutes'] is not None]
    actual_values = [r['actual_minutes'] for r in legacy] + [r['actual_minutes'] for r in period_logs]
    known_origins = {r['id'] for r in legacy} | {l.get('agenda_item_id') for l in period_logs}
    recorded = sum(r['id'] in known_origins for r in eligible)
    deadlines = dict(on_time=0, late=0, unresolved=0, upcoming=0, unknown=0)
    tasks = [dict(r) for r in con.execute('''SELECT id,due_on,completed_at,status FROM planner_tasks
        WHERE due_on BETWEEN ? AND ? AND (?='' OR course_id=?)''',(start,end,course_id,course_id))]
    for task in tasks:
        try:
            deadline = datetime.combine(datetime.fromisoformat(task['due_on']).date(),time.max,zone)
        except ValueError:
            deadlines['unknown'] += 1
            continue
        completed = instant(task['completed_at'])
        if completed and task['status'] not in ('completed',):
            deadlines['unknown'] += 1
        elif completed and completed <= now:
            deadlines['on_time' if completed <= deadline else 'late'] += 1
        elif task['status'] == 'completed' and completed is None:
            deadlines['unknown'] += 1
        else:
            deadlines['unresolved' if deadline < now else 'upcoming'] += 1
    carry = con.execute("SELECT COUNT(*) FROM task_rollover_events WHERE from_date BETWEEN ? AND ? AND decision='carry'",(start,end)).fetchone()[0]
    if course_id:
        carry = con.execute("SELECT COUNT(*) FROM task_rollover_events e JOIN planner_tasks t ON t.id=e.task_id WHERE from_date BETWEEN ? AND ? AND decision='carry' AND t.course_id=?",(start,end,course_id)).fetchone()[0]
    result = dict(planned_items=len(eligible),completed_items=sum(r['status']=='completed' for r in eligible),
        planned_focus_minutes=sum(r['planned_minutes'] or 0 for r in eligible),
        actual_focus_minutes=sum(actual_values) if actual_values else None,
        carry_forward_count=carry,missed_deadline_count=deadlines['late']+deadlines['unresolved'],
        recorded_items=recorded,deadline_outcomes=deadlines,
        unallocated_estimate_minutes=sum(r['planned_minutes'] or 0 for r in rows if r not in eligible),
        scope=scope,as_of=stamp,policy_version=POLICY_VERSION)
    refs = tuple('agenda_item:'+r['id'] for r in eligible) + tuple('work_log:'+r['id'] for r in period_logs)
    completed_refs = []
    if 'planner_command_receipts' in tables:
        receipts = [dict(r) for r in con.execute("""SELECT r.command_id,r.task_id,r.occurred_at
            FROM planner_command_receipts r JOIN planner_tasks t ON t.id=r.task_id
            WHERE r.action='completed' AND (?='' OR t.course_id=?)""",(course_id,course_id))]
        first = {}
        for receipt in receipts:
            occurred = instant(receipt['occurred_at'])
            if occurred and (receipt['task_id'] not in first or occurred < first[receipt['task_id']][0]):
                first[receipt['task_id']] = (occurred,receipt['command_id'])
        completed_refs = [command for occurred,command in first.values()
            if occurred <= now and start <= occurred.astimezone(zone).date().isoformat() <= end]
    result['distinct_completed_tasks'] = len(completed_refs) if 'planner_command_receipts' in tables else None
    today = now.astimezone(zone).date()
    upcoming = [dict(r) for r in con.execute("""SELECT id,estimated_minutes,due_on FROM planner_tasks
        WHERE status NOT IN ('completed','archived','skipped') AND due_on BETWEEN ? AND ?
        AND (?='' OR course_id=?)""",(today.isoformat(),(today+timedelta(days=6)).isoformat(),course_id,course_id))]
    workload = dict(known_minutes=sum(t['estimated_minutes'] for t in upcoming if t['estimated_minutes'] is not None),
        missing_estimate_count=sum(t['estimated_minutes'] is None for t in upcoming),task_count=len(upcoming))
    result['upcoming_workload'] = workload
    queue = []
    if 'planner_task_sources' in tables:
        queue = [dict(r) for r in con.execute("""SELECT t.id AS task_id,t.title,t.due_on AS next_review_on,
            s.owner,s.kind,s.identifier AS module_id,s.revision_key,s.sha256,s.mapping_status
            FROM planner_tasks t JOIN planner_task_sources s ON s.task_id=t.id
            WHERE t.status NOT IN ('completed','archived','skipped') AND t.due_on IS NOT NULL AND t.due_on<=?
            AND (?='' OR t.course_id=?) AND s.mapping_status='confirmed'
            ORDER BY t.due_on,t.id,s.identifier""", (end,course_id,course_id))]
        for source in queue:
            source['source_refs'] = [source['owner']+':'+source['module_id']+':'+source['revision_key']]
            source['current'] = False  # Only the source owner can verify freshness on open.
    result['revision_queue'] = queue
    comparison = None
    week_start = datetime.fromisoformat(start).date()
    if (datetime.fromisoformat(end).date()-week_start).days == 6 and 'evidence_json' in {r[1] for r in con.execute('PRAGMA table_info(weekly_reviews)')}:
        previous_start, previous_end = (week_start-timedelta(days=7)).isoformat(), (week_start-timedelta(days=1)).isoformat()
        row = con.execute('SELECT evidence_json FROM weekly_reviews WHERE week_start=? AND week_end=? AND closed_at IS NOT NULL', (previous_start,previous_end)).fetchone()
        if row and row[0]:
            prior = json.loads(row[0])
            old_scope = prior.get('scope', {})
            compatible = (prior.get('policy_version') == POLICY_VERSION and old_scope.get('timezone') == local_timezone
                          and old_scope.get('course_id','') == course_id and old_scope.get('start') == previous_start
                          and old_scope.get('end') == previous_end)
            complete_coverage = (result['planned_items'] > 0 and result['recorded_items'] == result['planned_items']
                                 and prior.get('planned_items',0) > 0 and prior.get('recorded_items') == prior.get('planned_items'))
            if compatible and complete_coverage and result['actual_focus_minutes'] is not None and prior.get('actual_focus_minutes') is not None:
                comparison = {'scheduled_minutes_delta':result['planned_focus_minutes']-prior['planned_focus_minutes'],
                              'actual_minutes_delta':result['actual_focus_minutes']-prior['actual_focus_minutes'],
                              'previous_start':previous_start,'previous_end':previous_end}
    result['metrics'] = {
        'upcoming_workload': Metric(workload,'minutes_and_tasks','partial' if workload['missing_estimate_count'] else 'available' if upcoming else 'empty',
            dict(start=today.isoformat(),end=(today+timedelta(days=6)).isoformat(),timezone=local_timezone,course_id=course_id),stamp,
            source_refs=tuple('planner_task:'+t['id'] for t in upcoming),exclusions=('No overload ratio without entered availability',)).to_dict(),
        'revision_queue': Metric(len(queue) if 'planner_task_sources' in tables else None,'items',('available' if queue else 'empty') if 'planner_task_sources' in tables else 'unavailable',scope,stamp,source_refs=tuple('planner_task:'+s['task_id'] for s in queue),exclusions=('Explicit source-linked study commitments with user-entered due dates only; source freshness revalidated on open',)).to_dict(),
        'weekly_comparison': Metric(comparison,'delta','available' if comparison is not None else 'unavailable',scope,stamp,
            exclusions=('Adjacent snapshots with comparable policy, scope and logging coverage required',)).to_dict(),
        'distinct_completed_tasks': Metric(result['distinct_completed_tasks'],'tasks',
            'available' if 'planner_command_receipts' in tables else 'unavailable',scope,stamp,
            source_refs=tuple('command:'+ref for ref in completed_refs),
            exclusions=('Undated historical completion has no terminal receipt',)).to_dict(),
        'scheduled_minutes': Metric(result['planned_focus_minutes'],'minutes','available' if eligible else 'empty',scope,stamp,source_refs=refs,exclusions=('Unapproved and unallocated estimates','Fixed classes and routines')).to_dict(),
        'actual_minutes': Metric(result['actual_focus_minutes'],'minutes','available' if recorded == len(eligible) and actual_values else 'partial' if actual_values else 'empty',scope,stamp,source_refs=refs,exclusions=('Self-reported effort; no mastery inference',)).to_dict(),
        'logging_coverage': Metric(None if not eligible else recorded/len(eligible),'ratio','available' if eligible else 'empty',scope,stamp,recorded,len(eligible),refs).to_dict(),
        'deadline_outcomes': Metric(deadlines,'tasks','available' if tasks else 'empty',scope,stamp,source_refs=tuple('planner_task:'+t['id'] for t in tasks)).to_dict()}
    return result
