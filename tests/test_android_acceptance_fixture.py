"""The emulator bundle uses production owners and never enters the app APK."""
import json
import sqlite3
import subprocess
import sys
import zipfile


def test_android_fixture_restores_production_lessons_and_assessments(tmp_path):
    result = subprocess.run([sys.executable, 'scripts/android_acceptance_fixture.py', str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    metadata = json.loads((tmp_path/'sessions.json').read_text())
    from personal_learning_assistant.android_backup import stage_restore, apply_pending_restore
    root = tmp_path/'restored'
    stage_restore(root, (tmp_path/'workspace.zip').read_bytes())
    apply_pending_restore(root)
    from personal_learning_assistant.services.assessment_execution_service import AssessmentExecutionService
    service = AssessmentExecutionService(root/'data/learning_assistant.db', production=True)
    for kind in ('online', 'paper'):
        state = service.state(metadata[kind])
        assert state['status'] == 'paused'
        assert len(state['questions']) == 2
    with sqlite3.connect(root/'data/learning_assistant.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT count(*) FROM knowledge_chunks').fetchone()[0] > 0
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='assessment_candidate_execution'").fetchone()
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.learning_studio.sources import RegisteredSources
    studio = LearningStudioService(root/'data/learning_studio.sqlite3',
        source_loader=RegisteredSources(root/'data/learning_assistant.db', {'documents': root/'data/documents'}),
        catalogue_loader=lambda: {'available':True,'courses':[]})
    assert studio.module('uc100n-demo', 1)['title'].startswith('UC100N-style demonstration')
    with zipfile.ZipFile(tmp_path/'workspace.zip') as archive:
        assert not any('test' in name or 'fixture-signing-key' in name for name in archive.namelist())
