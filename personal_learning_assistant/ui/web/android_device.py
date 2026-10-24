"""Phone-only user actions; existing owners retain academic persistence rules."""
from contextlib import closing
import hashlib
import io
from pathlib import Path
import sqlite3
from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file


def register_android_device(app, root):
    device=Blueprint('android_device',__name__)

    @device.get('/mobile/device')
    def settings():
        return render_template('android_device.html',active_page='mobile-settings',message='')

    @device.post('/mobile/device/course')
    def course():
        from personal_learning_assistant.services.course_service import CourseService
        from personal_learning_assistant.repositories.routed_course_repository import RoutedCourseRepository
        from personal_learning_assistant.domain.course_models import CreateCourseCommand
        try:
            CourseService(RoutedCourseRepository()).create_course(CreateCourseCommand(
                code=request.form.get('code','')[:30],name=request.form.get('name','')[:150],
                semester=request.form.get('semester','')[:100]))
        except ValueError:
            return render_template('android_device.html',active_page='mobile-settings',message='Check course code/name or use an existing course.'),400
        return redirect('/learning',code=303)

    @device.post('/mobile/device/restore-subjects')
    def restore_subjects():
        from personal_learning_assistant.services.android_subject_restore import restore_semester_one_subjects
        added = restore_semester_one_subjects()
        message = ('Restored missing Semester 1 subjects: ' + ', '.join(added) + '. '
                   if added else 'Your Semester 1 subjects are already registered. ')
        message += 'Original course templates are available in Learning Studio. Existing study progress was preserved.'
        return render_template('android_device.html',active_page='mobile-settings',message=message)

    def _register_local_pdf(upload):
        """Use the existing canonical source owner; never create a parallel Library store."""
        if upload is None or not upload.filename or not upload.filename.casefold().endswith('.pdf'):
            raise ValueError('Choose a PDF file from your device.')
        raw = upload.read(20 * 1024 * 1024 + 1)
        if not raw or len(raw) > 20 * 1024 * 1024 or not raw.startswith(b'%PDF-'):
            raise ValueError('Choose a valid PDF of at most 20 MB.')
        from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import SQLiteKnowledgeRegistryRepository
        from personal_learning_assistant.services.knowledge_registry_service import KnowledgeRegistryService
        from personal_learning_assistant.repositories.sqlite.ingestion_repository import SQLiteIngestionRepository
        from personal_learning_assistant.services.unified_ingestion_service import UnifiedIngestionService
        from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver
        digest = hashlib.sha256(raw).hexdigest()
        directory = root / 'data/documents'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (digest + '.pdf')
        # Immutable, content-addressed originals. Reject unexpected existing
        # files/symlinks instead of overwriting a source used by study records.
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
                raise ValueError('The local source identity has changed. No file was replaced.')
        else:
            with path.open('xb') as destination:
                destination.write(raw)
        with closing(sqlite3.connect(root / 'data/learning_assistant.db', isolation_level=None)) as con:
            con.row_factory = sqlite3.Row
            con.execute('PRAGMA foreign_keys=ON')
            registry = KnowledgeRegistryService(SQLiteKnowledgeRegistryRepository(con))
            registry.register_document(
                kind='document', path_key='documents/' + path.name,
                content_hash=digest, mime_type='application/pdf', size_bytes=len(raw))
            row = con.execute('SELECT id FROM knowledge_documents WHERE path_key=?',
                              ('documents/' + path.name,)).fetchone()
            if row is None:
                raise RuntimeError('Canonical source registration was not confirmed.')
            identity = row[0]
            extraction = UnifiedIngestionService(
                SQLiteIngestionRepository(con),
                SourceRootResolver({'documents': directory})).ingest_document(identity)
        app.extensions['academic_wal_publisher'].request_refresh()
        return identity, extraction.status

    @device.post('/mobile/device/source')
    def source():
        """Keep older Device Settings upload links working for installed clients."""
        try:
            identity, status = _register_local_pdf(request.files.get('source'))
        except ValueError:
            return render_template('android_device.html', active_page='mobile-settings',
                                   message='Choose a valid PDF of at most 20 MB. No source was changed.'), 400
        except (OSError, sqlite3.Error, RuntimeError):
            return render_template('android_device.html', active_page='mobile-settings',
                                   message='PDF could not be stored safely. Existing study records were kept.'), 503
        description = ('Text extraction complete.' if status in ('completed', 'matched')
                       else 'PDF stored, but text extraction is unavailable (for example, scanned pages without OCR).')
        return render_template('android_device.html', active_page='mobile-settings', message=
            'Source registered locally. Source ID: ' + identity + '. ' + description +
            ' Use this source ID and its original hash in an authored Learning package.')

    @device.post('/library/upload')
    def library_pdf_upload():
        """Library entry point for PDF registration on the private Android runtime."""
        from .routes import _tutor_action_token_matches
        if (not current_app.config.get('ANDROID_LOCAL_RUNTIME')
                or not current_app.config.get('LEARNING_LIBRARY_ENABLED', True)):
            abort(404)
        if not _tutor_action_token_matches():
            abort(403)
        if request.content_length is not None and request.content_length > 21 * 1024 * 1024:
            return 'PDF upload exceeds the 20 MB limit.', 413
        try:
            identity, status = _register_local_pdf(request.files.get('source'))
        except ValueError:
            return 'Choose a valid .pdf file of at most 20 MB. Existing study records were kept.', 400
        except (OSError, sqlite3.Error, RuntimeError):
            return 'PDF could not be stored safely. Existing study records were kept.', 503
        return redirect('/library?pdf_status=' + (
            'extracted' if status in ('completed', 'matched') else 'stored'
        ) + '&source_id=' + identity + '#library-pdf-upload', code=303)

    @device.post('/mobile/device/tutor-index')
    def tutor_index():
        from .routes import _tutor_action_token_matches
        if not _tutor_action_token_matches():
            abort(403)
        from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder, RetrievalIndexBuildError
        from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
        try:
            database=root/'data/learning_assistant.db'
            with closing(sqlite3.connect(database.absolute().as_uri()+'?mode=ro',uri=True)) as con:
                # A derived lexical index only: no model download, external call,
                # academic mutation or stale-index bypass.
                RetrievalIndexBuilder(SQLiteRetrievalSourceRepository(con),root/'data/tutor_retrieval').build(embedding_provider=None,acknowledge=False)
        except (RetrievalIndexBuildError,sqlite3.Error,OSError):
            return render_template('android_device.html',active_page='mobile-settings',
                message='Tutor index could not be built. Add a PDF with extractable text, then try again. Your study records were kept.'),409
        return redirect('/agent',code=303)

    @device.get('/mobile/device/export')
    def export():
        from personal_learning_assistant.android_backup import export_backup
        try: raw=export_backup(root)
        except (ValueError,OSError,sqlite3.Error):abort(409)
        return send_file(io.BytesIO(raw),mimetype='application/zip',as_attachment=True,download_name='ANVAYA-private-backup.zip')

    @device.post('/mobile/device/restore')
    def restore():
        from personal_learning_assistant.android_backup import stage_restore
        upload=request.files.get('backup')
        if upload is None:abort(400)
        try:stage_restore(root,upload.read(100*1024*1024+1))
        except (ValueError,OSError,sqlite3.Error):
            return render_template('android_device.html',active_page='mobile-settings',message='Backup rejected. Current data was kept.'),400
        return render_template('android_device.html',active_page='mobile-settings',message=
            'Backup verified and staged. Save or pause your work, then close ANVAYA using the link below and reopen its icon. Current data is retained as a recovery copy.')

    @device.get('/mobile/restart')
    def restart_help():
        return 'Save and pause your work. Force stop ANVAYA from Android App info, then reopen.'

    app.register_blueprint(device)
