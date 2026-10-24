#!/usr/bin/env python3
"""Read source code; write only disposable data and an optional JSON report.

Run: PYTHONDONTWRITEBYTECODE=1 python reproduce_topic_contracts.py --repo /path/to/repo --output topic_characterization.json
Desired A/D safety is asserted using synthetic evidence only.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import importlib.util
import json
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path(os.environ.get('REPO_ROOT', Path.cwd())), help='Source checkout (default: REPO_ROOT, otherwise current directory)')
parser.add_argument('--output', type=Path, help='Optional output JSON path; otherwise print JSON to stdout')
args = parser.parse_args()
REPO = args.repo.resolve()
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location('phase_f_fixture', REPO / 'tests/test_assessment_studio_phase_f.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
from personal_learning_assistant.services.adaptive_academic_loop_service import AdaptiveAcademicLoopService
from personal_learning_assistant.repositories.sqlite.assessment_intelligence_repository import SQLiteAssessmentIntelligenceRepository

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

with tempfile.TemporaryDirectory(prefix='topic-audit-') as folder:
    path = fixture._database(Path(folder))
    before = digest(path)
    intelligence = AssessmentIntelligenceService(path)
    weak = intelligence.weak_topics()
    preview = AdaptiveAcademicLoopService(path).preview()
    rank = next(x for x in weak['topics'] if x['topic_id'] == 'topic-rank')
    candidate = next((x for x in preview['candidates'] if x['topic_id'] == 'topic-rank'), None)
    assert rank['weighted_performance_percent'] == 100.0 and rank['band'] == 'strong'
    assert candidate is None
    lu_diagnostic = next(x for x in preview['candidates'] if x['topic_id'] == 'topic-lu')
    assert lu_diagnostic['action_family'] == 'evidence_check' and lu_diagnostic['suggested_priority'] == 'P2'
    assert digest(path) == before
    with closing(sqlite3.connect(path)) as db, db:
        counts = {table: db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                  for table in ('assessment_recovery_recommendations','planner_tasks')}
        assert counts == {'assessment_recovery_recommendations': 0, 'planner_tasks': 0}
        columns = [r[1] for r in db.execute('PRAGMA table_info(assessment_test_session_questions)')]
        schema = {table: [r[1] for r in db.execute('PRAGMA table_info('+table+')')]
                  for table in ('question_topic_mappings','assessment_import_question_specs',
                                'assessment_response_evaluations','assessment_test_sessions')}
        original = SQLiteAssessmentIntelligenceRepository(db).list_confirmed_question_evidence()
        db.execute("INSERT INTO question_topic_mappings (id,question_id,topic_id,score,rank,method,state,reason,created_at,reviewed_at) VALUES ('uncertain-q1','q1','topic-lu',0.1,1,'synthetic-uncertain','confirmed','fixture only',?,NULL)", (fixture.NOW,))
        db.commit()
        changed_mapping = SQLiteAssessmentIntelligenceRepository(db).list_confirmed_question_evidence()
        assert changed_mapping == original
        assert all(row['confidence'] == 1.0 for row in original)
        missing = [field for field in ('mapping_id','mapping_state','mapping_confidence',
                   'mapping_method','mapping_reviewed_at','mapping_review_required') if field not in columns]
        assert len(missing) == 6
        assert all(row['mapping_state'] == 'unknown' and row['mapping_id'] is None
                   and row['mapping_reviewed_at'] is None and row['mapping_review_required'] is True
                   and row['automatic_remediation_eligible'] is False for row in original)
        # Evaluation confidence, independently of mapping confidence, controls weighting.
        db.execute("UPDATE assessment_response_evaluations SET confidence=0.1 WHERE id='ev-sq1'")
        db.commit()
    updated_lu = next(x for x in intelligence.weak_topics()['topics'] if x['topic_id'] == 'topic-lu')
    assert updated_lu['question_count'] == 2
    assert updated_lu['performance_percent'] == 12.5
    assert updated_lu['weighted_performance_percent'] == 22.7
    result = {
        'repository': str(REPO), 'baseline': 'f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf',
        'scenario_A': {'strong_topic': rank, 'recovery_candidate': candidate,
                       'unqualified_failure_diagnostic': lu_diagnostic,
                       'main_database_hash_unchanged_on_reads': True, 'ledger_and_task_counts': counts},
        'scenario_D': {'returned_keys': sorted(original[0]), 'evidence_sample': original[0],
                       'session_question_columns': columns, 'missing_mapping_snapshot_fields': missing,
                       'related_table_columns': schema, 'confirmed_mapping_score_0_1_unreviewed_has_no_effect': True,
                       'unknown_mapping_excluded_from_automatic_remediation': True,
                       'grading_confidence_0_1_still_counted': updated_lu},
        'scope': 'Synthetic fixture only. No network/provider, production DB or vault access. No source edits.'
    }
    serialized = json.dumps(result, indent=2, default=str)+'\n'
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding='utf-8')
        print(json.dumps({'scenario_A':'desired behavior pass','scenario_D':'desired behavior pass','report':str(output)},indent=2))
    else:
        print(serialized)
