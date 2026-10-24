"""Generate synthetic-only Android instrumentation assets, outside the app APK.

This script is called by CI before assembleDebugAndroidTest. No fixture routes,
test helpers or demonstration records are shipped in the production application.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
from copy import deepcopy
import sqlite3
import sys
import tempfile
from uuid import uuid4

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(REPOSITORY/'tests'))


def generate(destination):
    from tests.test_assessment_studio_phase_b import _database, _package, _subjective_package, _raw
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.services.assessment_execution_service import AssessmentExecutionService
    from tests.academic_evidence_v23_fixtures import source_pdf, authored_sample
    from personal_learning_assistant.android_backup import export_backup
    from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
    from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
    from personal_learning_assistant.repositories.sqlite.ingestion_repository import SQLiteIngestionRepository
    from personal_learning_assistant.services.unified_ingestion_service import UnifiedIngestionService
    from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.learning_studio.sources import RegisteredSources

    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='anvaya-android-synthetic-') as temporary:
        folder = Path(temporary)
        root = folder/'workspace'
        data = root/'data'
        documents = data/'documents'
        documents.mkdir(parents=True)
        database = _database(data)
        apply_migrations(database, enable_extended_assessment=True)
        importer = AssessmentPackageService(database)
        service = AssessmentExecutionService(database, production=True)
        sessions = {}
        for kind in ('online', 'paper', 'paper_restart'):
            assessment = _package() if kind == 'online' else _subjective_package()
            assessment['package_id'] = 'android-acceptance-' + kind
            assessment['assessment']['mode'] = 'practice'
            assessment['assessment']['title'] = 'Synthetic Android '+kind+' practice'
            if kind == 'online':
                assessment['questions'] = [deepcopy(assessment['questions'][0]) for _ in range(2)]
                assessment['questions'][1]['id'] = 'q2'
                assessment['questions'][1]['number'] = '2'
                assessment['assessment']['total_marks'] = 2
            else:
                q = assessment['questions'][0]
                q['rubric'] = json.dumps({'schema':'anvaya.subjective-rubric','version':1,
                    'question_id':q['id'],'total_marks_milli':3000,'grading_increment_milli':500,
                    'steps':[{'id':key,'label':label,'expected_work':work,'max_marks_milli':1000,
                        'prerequisites':deps,'award_when':['Correct method'],
                        'do_not_award_when':['Unsupported conclusion'],'allowed_awards_milli':[0,500,1000],
                        'alternative_group':None} for key,label,work,deps in [
                            ('factor','Factorization','State A = LU.',[]),
                            ('forward','Forward substitution','Solve Ly = b.',['factor']),
                            ('back','Backward substitution','Solve Ux = y.',['forward'])]],
                    'common_mistakes':['Interchanging the triangular solves'],'review_required':False})
            batch = importer.stage_upload(kind+'.json', _raw(assessment))
            aid = importer.approve(batch['id'])
            sid = AssessmentRunnerService(database).start(aid, confirmed=True)['session_id']
            service.adopt(sid, kind='online_timed' if kind == 'online' else 'paper_subjective',
                          self_review_acknowledged=kind != 'online')
            # Paused clocks do not expire while the emulator boots.
            service.command(sid, 'pause', {'expected_revision':service.state(sid)['revision'],
                                          'request_id':str(uuid4())})
            sessions[kind] = sid
        raw = source_pdf()
        digest = hashlib.sha256(raw).hexdigest()
        path = documents/(digest+'.pdf')
        path.write_bytes(raw)
        with closing(sqlite3.connect(database, isolation_level=None)) as con:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con)).register_document(
                kind='document', path_key='documents/'+path.name,
                content_hash=digest, mime_type='application/pdf', size_bytes=len(raw))
            identity = con.execute('SELECT id FROM knowledge_documents').fetchone()[0]
            UnifiedIngestionService(SQLiteIngestionRepository(con),
                SourceRootResolver({'documents': documents})).ingest_document(identity)
        package, assets = authored_sample(raw)
        package['source']['source_id'] = identity
        package['mapping'] = None
        studio = LearningStudioService(data/'learning_studio.sqlite3',
            source_loader=RegisteredSources(database, {'documents': documents}),
            catalogue_loader=lambda: {'available':True,'courses':[]})
        studio.stage(package, assets)
        studio.publish('uc100n-demo', 1)
        (destination/'workspace.zip').write_bytes(export_backup(root))
        (destination/'sessions.json').write_text(json.dumps({**sessions,
            'source_id': identity, 'synthetic_only': True}), encoding='utf-8')


if __name__ == '__main__':
    generate(sys.argv[1])
