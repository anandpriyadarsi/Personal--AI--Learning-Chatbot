"""Reproduction PASS means the known defect is present, not product acceptance."""
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
        record_testsuite_property(finding, 'REPRODUCED; desired behaviour FAIL; owner ' + owner + '; ' + future_test)
    for name in ['topic', 'planning', 'read_routes']:
        output = directory / (name + '.json')
        result = subprocess.run([sys.executable, str(ROOT / ('scripts/characterization/' + name + '.py')),
                                 '--repo', str(ROOT), '--output', str(output)], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        reports[name] = json.loads(output.read_text(encoding='utf-8'))
    return reports


@pytest.mark.known_defect
@pytest.mark.parametrize('finding', list(OWNERS))
def test_current_defect_reproduction(evidence, finding):
    topic, planning = evidence['topic'], evidence['planning']
    if finding == 'A':
        assert topic['scenario_A']['strong_topic']['weighted_performance_percent'] == 100
        assert topic['scenario_A']['recovery_candidate']['action_family'] == 'evidence_check'
    elif finding == 'B':
        assert planning['scenario_B']['actual_placement'][:10] < planning['scenario_B']['preferred_day']
    elif finding == 'C':
        assert all('data/learning_memory.json' in row['created'] for row in evidence['read_routes'] if row['state'] == 'seeded')
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


def test_characterizations_preserve_read_only_sql_and_report_filesystem_effects(evidence):
    assert evidence['topic']['scenario_A']['ledger_and_task_counts'] == {'assessment_recovery_recommendations': 0, 'planner_tasks': 0}
    assert evidence['planning']['scenario_B']['read_logical_dump_unchanged']
    assert all(row['status'] == 200 and not row['network_attempts'] for row in evidence['read_routes'])
