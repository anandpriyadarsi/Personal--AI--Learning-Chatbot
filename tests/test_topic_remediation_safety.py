"""A/D safety regressions use disposable synthetic assessment evidence only."""
from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from personal_learning_assistant.repositories.sqlite.assessment_intelligence_repository import (
    SQLiteAssessmentIntelligenceRepository,
)
from personal_learning_assistant.services.adaptive_academic_loop_service import (
    AdaptiveAcademicLoopConflictError, AdaptiveAcademicLoopService,
)
from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
from tests.test_assessment_studio_phase_f import _database, NOW


@pytest.mark.parametrize('single_bad_answer', [False, True])
def test_strong_topic_has_no_automatic_recovery_candidate(tmp_path, single_bad_answer):
    path = _database(tmp_path)
    if single_bad_answer:
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE assessment_test_session_questions SET topic_id='topic-rank', max_marks_milli=1000 WHERE id='sq1'")
            db.execute("UPDATE assessment_response_evaluations SET max_marks_milli=1000 WHERE id='ev-sq1'")
    observed = AssessmentIntelligenceService(path).weak_topics()
    strong = next(t for t in observed['topics'] if t['topic_id'] == 'topic-rank')
    assert strong['weighted_performance_percent'] == (80 if single_bad_answer else 100)
    assert strong['band'] == 'strong'
    assert 'lower relative observed performance' not in strong['recovery_signals']
    preview = AdaptiveAcademicLoopService(path).preview()
    assert all(t['topic_id'] != 'topic-rank' for t in preview['candidates'])
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM assessment_recovery_recommendations').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM planner_tasks').fetchone()[0] == 0


@pytest.mark.parametrize('submitted_at', [NOW, '2025-01-01T12:00:00Z', None])
def test_one_bad_answer_and_many_mistakes_remain_diagnostic_only(tmp_path, submitted_at):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE assessment_test_session_questions SET topic_id='topic-rank' WHERE id='sq2'")
        db.execute("UPDATE assessment_test_sessions SET submitted_at=? WHERE id='s1'", (submitted_at,))
        for i, category in enumerate(['careless', 'formula_recall', 'wrong_method']):
            db.execute("INSERT INTO assessment_evaluation_mistakes (id,response_evaluation_id,category,source_type,status,created_at) VALUES (?,'ev-sq1',?,'user','confirmed',?)", (f'extra-{i}', category, NOW))
    lu = next(t for t in AdaptiveAcademicLoopService(path).preview()['candidates'] if t['topic_id'] == 'topic-lu')
    assert lu['action_family'] == 'evidence_check'
    assert lu['suggested_priority'] == 'P2'
    assert lu['evidence']['automatic_remediation_eligible'] is False
    assert 'independent' in lu['suggested_description'].lower()
    assert 'mapping' in lu['suggested_description'].lower()


def test_legacy_multi_question_failure_never_implies_qualified_independent_evidence(tmp_path):
    path = _database(tmp_path)
    topic = next(t for t in AssessmentIntelligenceService(path).weak_topics()['topics'] if t['topic_id'] == 'topic-lu')
    assert topic['question_count'] == 2 and topic['weighted_performance_percent'] == 12.5
    assert topic['automatic_remediation_eligible'] is False
    assert {'mapping_snapshot_unknown', 'independence_unknown'} <= set(topic['remediation_exclusion_reasons'])
    lu = next(t for t in AdaptiveAcademicLoopService(path).preview()['candidates'] if t['topic_id'] == 'topic-lu')
    assert lu['action_family'] == 'evidence_check' and lu['suggested_priority'] == 'P2'


@pytest.mark.parametrize('score,reviewed_at', [(0.1, None), (1.0, NOW), (1.0, '2025-01-01T00:00:00Z')])
def test_unknown_snapshot_mapping_is_excluded_despite_current_mapping(tmp_path, score, reviewed_at):
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        repository = SQLiteAssessmentIntelligenceRepository(db)
        before = repository.list_confirmed_question_evidence()
        db.execute("INSERT INTO question_topic_mappings (id,question_id,topic_id,score,rank,method,state,created_at,reviewed_at) VALUES ('current','q1','topic-lu',?,1,'human','confirmed',?,?)", (score, NOW, reviewed_at))
        after = repository.list_confirmed_question_evidence()
    assert before == after
    first = next(t for t in after if t['response_evaluation_id'] == 'ev-sq1')
    assert first['mapping_id'] is None
    assert first['mapping_state'] == 'unknown' and first['mapping_confidence'] is None
    assert first['mapping_method'] is None and first['mapping_reviewed_at'] is None
    assert first['mapping_review_required'] is True
    assert first['independence_status'] == 'unknown'
    assert first['automatic_remediation_eligible'] is False
    assert first['confidence'] == 1.0  # Grading confidence cannot substitute for mapping confidence.
    diagnostic = next(t for t in AdaptiveAcademicLoopService(path).preview()['candidates'] if t['topic_id'] == 'topic-lu')
    assert diagnostic['action_family'] == 'evidence_check' and diagnostic['suggested_priority'] == 'P2'


def test_session_analysis_keeps_historical_mapping_unreviewed(tmp_path):
    from tests.test_assessment_studio_phase_e import _database as intelligence_database
    analysis = AssessmentIntelligenceService(intelligence_database(tmp_path)).session_analysis('s1')
    assert len(analysis['questions']) == 2
    for question in analysis['questions']:
        assert question['mapping_id'] is None and question['mapping_state'] == 'unknown'
        assert question['mapping_review_required'] is True and question['mapping_reviewed_at'] is None
        assert question['automatic_remediation_eligible'] is False


def _saved_diagnostic(path):
    service = AdaptiveAcademicLoopService(path)
    candidate = next(t for t in service.preview()['candidates'] if t['topic_id'] == 'topic-lu')
    generated = service.generate([candidate['evidence_fingerprint']])
    return service, service.recommendation(generated['results'][0]['recommendation_id'])


def _logical_dump(path):
    with closing(sqlite3.connect(path)) as db:
        return tuple(db.iterdump())


@pytest.mark.parametrize('status', ['pending', 'accepted'])
@pytest.mark.parametrize('evidence_version', ['assessment-intelligence-recovery-v1', ''])
def test_legacy_saved_recommendation_cannot_write_planner_or_rewrite_history(tmp_path, status, evidence_version):
    path = _database(tmp_path)
    service, recommendation = _saved_diagnostic(path)
    legacy_evidence = dict(recommendation['evidence'], version=evidence_version)
    legacy_evidence.pop('automatic_remediation_eligible')
    legacy_evidence.pop('remediation_exclusion_reasons')
    legacy_fingerprint = hashlib.sha256(json.dumps(legacy_evidence, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    old_payload = {'title': 'Old urgent rebuilding plan', 'description': 'Old evidence',
                   'priority': 'P0', 'estimated_minutes': 60, 'course_id': 'course-ma', 'topic_id': 'topic-lu'}
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE assessment_recovery_recommendations SET evidence_version=?, evidence_json=?, evidence_fingerprint=?, "
                   "action_family='concept_rebuild', suggested_priority='P0', status=?, applied_payload_json=? "
                   "WHERE id=?", (evidence_version, json.dumps(legacy_evidence), legacy_fingerprint, status,
                                  json.dumps(old_payload) if status == 'accepted' else '{}', recommendation['id']))
    before = _logical_dump(path)
    with pytest.raises(AdaptiveAcademicLoopConflictError, match='[Rr]efresh.*generate'):
        service.apply(recommendation['id'], {'revision': recommendation['revision']})
    assert _logical_dump(path) == before
    assert service.recommendation(recommendation['id'])['status'] == status
    # Refresh/generate can create a new proposal; no historical row is relabeled
    # as current evidence by the blocked Apply operation.
    fresh = next(t for t in service.preview()['candidates'] if t['topic_id'] == 'topic-lu')
    generated = service.generate([fresh['evidence_fingerprint']])
    assert generated['created_count'] == 1
    reviewed = service.recommendation(generated['results'][0]['recommendation_id'])
    assert reviewed['action_family'] == 'evidence_check' and reviewed['suggested_priority'] == 'P2'


def test_pending_current_diagnostic_requires_current_candidate_before_writes(tmp_path):
    path = _database(tmp_path)
    service, recommendation = _saved_diagnostic(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE assessment_response_evaluations SET awarded_marks_milli=2000, outcome='correct'")
    assert service.preview()['candidates'] == ()
    before = _logical_dump(path)
    with pytest.raises(AdaptiveAcademicLoopConflictError, match='[Rr]efresh.*generate'):
        service.apply(recommendation['id'], {'revision': recommendation['revision']})
    assert _logical_dump(path) == before


def test_applied_legacy_history_remains_read_only_and_idempotent(tmp_path):
    path = _database(tmp_path)
    service, recommendation = _saved_diagnostic(path)
    applied = service.apply(recommendation['id'], {'revision': recommendation['revision']})
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE assessment_recovery_recommendations SET evidence_version='assessment-intelligence-recovery-v1' WHERE id=?", (applied['id'],))
    historical = service.recommendation(applied['id'])
    before = _logical_dump(path)
    assert service.apply(applied['id'], {'priority': 'P0'}) == historical
    assert _logical_dump(path) == before


def test_all_strong_topics_render_no_diagnostic_without_claiming_no_evidence(tmp_path):
    from tests.test_assessment_studio_phase_f import _app
    path = _database(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE assessment_response_evaluations SET awarded_marks_milli=max_marks_milli, outcome='correct'")
    before = _logical_dump(path)
    response = _app(path).test_client().get('/assessments/adaptive')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'No diagnostic is currently recommended' in html
    assert 'Observed grading outcomes may still be available' in html
    assert 'No confirmed topic evidence is currently available' not in html
    assert _logical_dump(path) == before


def test_session_route_displays_unreviewed_topic_provenance_and_preserves_scores(tmp_path):
    from tests.test_assessment_studio_phase_e import _app, _database as intelligence_database
    path = intelligence_database(tmp_path)
    before = _logical_dump(path)
    response = _app(path).test_client().get('/assessments/sessions/s1/analysis')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'Historical mapping review and independence are unknown' in html
    assert html.count('Mapping: Unknown') == 2
    assert html.count('review required; independence: Unknown') == 2
    assert '1 / 2' in html and '2 / 2' in html
    assert _logical_dump(path) == before
