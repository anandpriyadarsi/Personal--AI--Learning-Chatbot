"""A/B/D/P reproduction remains; C is desired B2 read-safety acceptance."""
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
OWNERS = {
    'A': ('C', 'test_strong_topic_has_no_automatic_recovery_candidate'),
    'B': ('E', 'test_future_preferred_date_not_selected_early'),
    'C': ('B', 'test_get_missing_legacy_files_does_not_create_files'),
    'D': ('B', 'test_unknown_snapshot_mapping_is_excluded'),
    'P01': ('E', 'test_approved_day_primary_view_uses_saved_items_and_totals'),
    'P02': ('E', 'test_task_deadline_is_marker_not_fixed_routine_or_duplicate_work'),
    'P03': ('E', 'test_tomorrow_respects_reviewed_rollover_decisions'),
    'P04': ('E', 'test_count_recurrence_day_week_month_equal_filtered_global_series'),
    'P05': ('E', 'test_recurring_event_with_end_time_survives_later_window'),
    'P06': ('E', 'test_changed_month_revision_preserves_history_and_updates_owned_entities'),
    'P07': ('E', 'test_saved_study_and_tasks_share_total_capacity_and_deep_limit'),
    'P08': ('E', 'test_completion_creates_one_engagement_and_suppresses_completed_source'),
}


@pytest.fixture(scope='module')
def evidence(tmp_path_factory, record_testsuite_property):
    directory = tmp_path_factory.mktemp('characterization')
    reports = {}
    for finding, (owner, future_test) in OWNERS.items():
        status = 'DESIRED read safety PASS' if finding == 'C' else 'REPRODUCED; desired behaviour FAIL'
        record_testsuite_property(finding, status + '; owner ' + owner + '; ' + future_test)
    for name in ['topic', 'planning', 'read_routes']:
        output = directory / (name + '.json')
        result = subprocess.run([sys.executable, str(ROOT / ('scripts/characterization/' + name + '.py')),
                                 '--repo', str(ROOT), '--output', str(output)], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        reports[name] = json.loads(output.read_text(encoding='utf-8'))
    return reports


@pytest.mark.known_defect
@pytest.mark.parametrize('finding', [f for f in OWNERS if f != 'C'])
def test_current_defect_reproduction(evidence, finding):
    topic, planning = evidence['topic'], evidence['planning']
    if finding == 'A':
        assert topic['scenario_A']['strong_topic']['weighted_performance_percent'] == 100
        assert topic['scenario_A']['recovery_candidate']['action_family'] == 'evidence_check'
    elif finding == 'B':
        assert planning['scenario_B']['actual_placement'][:10] < planning['scenario_B']['preferred_day']
    elif finding == 'D':
        assert len(topic['scenario_D']['missing_mapping_snapshot_fields']) == 6
    elif finding == 'P01':
        assert planning['scenario_B']['approved_title'] != planning['scenario_B']['above_saved_preview_title']
    elif finding == 'P02':
        assert len(planning['due_marker_duplicate']) == 2
    elif finding == 'P03':
        assert planning['rollover_policy_not_consumed']['dropped_reappeared']
    elif finding == 'P04':
        assert planning['calendar_window_inconsistency']['day_count_dates'] == ['2026-10-12']
    elif finding == 'P05':
        assert planning['calendar_window_inconsistency']['month_class_on_oct12'] and not planning['calendar_window_inconsistency']['day_class_on_oct12']
    elif finding == 'P06':
        assert 'UNIQUE constraint failed' in planning['month_revision_failure']['root_cause']
        assert planning['month_revision_failure']['rollback_logical_dump_unchanged']
    elif finding == 'P07':
        row = planning['study_capacity_and_completion']
        assert row['total_selected_focus_minutes'] == 1080 > row['summary_focus_minutes']
    elif finding == 'P08':
        row = planning['study_capacity_and_completion']
        assert row['completed_agenda_source_status'] == 'planned' and row['engagement_rows'] == 0


def test_get_missing_legacy_files_does_not_create_files(evidence):
    # Retires the inverted C assertion only after B2 desired regressions passed.
    # The optimized single-snapshot probe must still cover all four GET cases.
    assert len(evidence['read_routes']) == 4
    assert {(row['route'], row['state']) for row in evidence['read_routes']} == {
        ('/planning', 'empty'), ('/analysis', 'empty'),
        ('/planning', 'seeded'), ('/analysis', 'seeded'),
    }
    assert all(not row['created'] and not row['changed'] and not row['writes']
               for row in evidence['read_routes'])


def test_characterizations_preserve_read_only_sql_and_report_filesystem_effects(evidence):
    assert evidence['topic']['scenario_A']['ledger_and_task_counts'] == {'assessment_recovery_recommendations': 0, 'planner_tasks': 0}
    assert evidence['planning']['scenario_B']['read_logical_dump_unchanged']
    assert all(row['status'] == 200 and not row['network_attempts'] for row in evidence['read_routes'])


@pytest.mark.parametrize('probe', ['planning', 'topic'])
def test_probe_closes_connections_before_temporary_directory_cleanup(tmp_path, probe):
    # Emulate Windows' refusal to delete an open SQLite file even on Linux.
    # Weak references retain no connection that CPython would normally release.
    check = r'''
import runpy, sqlite3, sys, tempfile, weakref
refs = []
connect = sqlite3.connect
class TrackedConnection(sqlite3.Connection):
    closed = False
    def close(self):
        self.closed = True
        return super().close()
def tracked(*args, **kwargs):
    kwargs.setdefault('factory', TrackedConnection)
    connection = connect(*args, **kwargs)
    refs.append(weakref.ref(connection))
    return connection
sqlite3.connect = tracked
TemporaryDirectory = tempfile.TemporaryDirectory
class CheckedDirectory(TemporaryDirectory):
    def __exit__(self, *args):
        active = [r() for r in refs if r() is not None and not r().closed]
        try:
            assert not active, 'SQLite handles still open at directory cleanup'
        finally:
            for connection in active:
                connection.close()
            super().__exit__(*args)
tempfile.TemporaryDirectory = CheckedDirectory
script, repo, output = sys.argv[1:]
sys.argv = [script, '--repo', repo, '--output', output]
runpy.run_path(script, run_name='__main__')
'''
    script = ROOT / 'scripts/characterization' / (probe + '.py')
    result = subprocess.run([sys.executable, '-c', check, str(script), str(ROOT), str(tmp_path / 'report.json')],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('path_type', ['PurePosixPath', 'PureWindowsPath'])
def test_read_route_hash_inventory_uses_portable_relative_paths(tmp_path, path_type):
    # Execute the actual child hash function with both pathlib path flavours.
    # Only filesystem enumeration is supplied; hashing reads real fixture bytes.
    import ast
    import hashlib
    import pathlib

    script = ast.parse((ROOT / 'scripts/characterization/read_routes.py').read_text(encoding='utf-8'))
    child = next(ast.literal_eval(n.value) for n in script.body
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'child' for t in n.targets))
    function = next(n for n in ast.parse(child).body if isinstance(n, ast.FunctionDef) and n.name == 'hashes')
    fixture = tmp_path / 'learning_memory.json'
    fixture.write_bytes(b'{"synthetic": true}')

    class Entry:
        def is_file(self):
            return True

        def relative_to(self, root):
            return getattr(pathlib, path_type)('data', fixture.name)

        def read_bytes(self):
            return fixture.read_bytes()

    class Root:
        def rglob(self, pattern):
            return [Entry()]

    namespace = {'root': Root(), 'hashlib': hashlib}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual probe hashes>', 'exec'), namespace)
    assert namespace['hashes']() == {'data/learning_memory.json': hashlib.sha256(fixture.read_bytes()).hexdigest()}
