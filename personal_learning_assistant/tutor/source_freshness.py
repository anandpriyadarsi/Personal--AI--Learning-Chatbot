"""Read-only source identity/version checks shared by both Tutor workspaces."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
from urllib.parse import quote
from personal_learning_assistant.repositories.sqlite.search_metadata_repository import SQLiteSearchMetadataRepository


class TutorSourceChangedError(RuntimeError):
    pass


def source_snapshot(connection, session, document_ids=()):
    ids = set(document_ids)
    selected = str(session.metadata.get('source_document_id') or '')
    if selected:
        ids.add(selected)
    result = []
    metadata = SQLiteSearchMetadataRepository(connection)
    for did in sorted(ids):
        row = connection.execute('SELECT * FROM knowledge_documents WHERE id=?', (did,)).fetchone()
        item = metadata.document(did)
        if row is None or item is None or row['extraction_status'] != 'completed':
            raise TutorSourceChangedError('Source unavailable. Review or reselect your sources.')
        if did == selected and session.metadata.get('source_version_hash') != item['version_hash']:
            raise TutorSourceChangedError('Source changed. Open its current version and start a new scoped conversation.')
        if session.course_id and session.course_id not in item['course_ids']:
            # Native placements use their authoritative locator scope below.
            if not str(row['path_key']).startswith('native_library/'):
                raise TutorSourceChangedError('Source moved outside this course. Review your selection.')
        snapshot = {'id':did, 'hash':item['version_hash'], 'courses':list(item['course_ids']),
                    'resources':list(item['resource_ids']), 'topics':list(item['topic_ids']),
                    'extraction_version':row['extraction_version']}
        # Native published chunks carry exact identity, generation and metadata revision.
        from personal_learning_assistant.ingestion.chunking import decode_chunk_type
        locators = connection.execute('SELECT chunk_type FROM knowledge_chunks WHERE document_id=? AND extraction_version=?', (did,row['extraction_version'])).fetchall()
        native_locators = [decode_chunk_type(r[0])[1] for r in locators]
        native_locators = [x for x in native_locators if x.get('native_document_id')]
        if str(row['path_key']).startswith('native_library/') and not native_locators:
            raise TutorSourceChangedError('Library publication is incomplete. Rebuild the index before sending.')
        if native_locators:
            # Reuse canonical retrieval's pinned course aliases and native policy.
            from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import SQLiteRetrievalSourceRepository
            current_records = [r for r in SQLiteRetrievalSourceRepository(connection).active_records() if r['document_id']==did]
            if not current_records:
                raise TutorSourceChangedError('Library publication changed. Review or rebuild its index.')
            native_locators = [r['locator'] for r in current_records]
            effective_courses = sorted({c for r in current_records for c in r['course_ids']})
            if session.course_id and session.course_id not in effective_courses:
                raise TutorSourceChangedError('Library source moved outside this course. Review your selection.')
            snapshot['courses'] = effective_courses
            db = connection.execute('PRAGMA database_list').fetchone()[2]
            root = Path(db).resolve().parent / 'native_library'
            uri = 'file:' + quote((root/'library.sqlite3').as_posix(),safe='/:') + '?mode=ro'
            try:
                from personal_learning_assistant.services.native_document_library import _verified_original
                with closing(sqlite3.connect(uri,uri=True)) as native:
                    native.row_factory = sqlite3.Row
                    seen = []
                    for loc in native_locators:
                        doc = native.execute('SELECT * FROM documents WHERE id=?', (loc['native_document_id'],)).fetchone()
                        linked = native.execute("SELECT 1 FROM source_links WHERE document_id=? AND namespace='canonical' AND source_id=? AND content_hash=?", (loc['native_document_id'],did,item['version_hash'])).fetchone()
                        if (not doc or not linked or doc['trashed_at'] or not doc['indexing_enabled']
                            or doc['sha256'] != item['version_hash'] or doc['generation'] != loc.get('native_generation')
                            or doc['metadata_revision'] != loc.get('metadata_revision')
                            or doc['availability'] != 'available'):
                            raise TutorSourceChangedError('Library source changed or indexing was disabled. Review your selection.')
                        _verified_original(root,dict(doc))
                        identity = {k:loc.get(k) for k in ('native_document_id','native_generation','metadata_revision','content_hash','course_id')}
                        if identity not in seen:
                            seen.append(identity)
                    snapshot['native'] = seen
            except TutorSourceChangedError:
                raise
            except Exception as exc:
                raise TutorSourceChangedError('Original Library source is unavailable. Review your selection.') from exc
        result.append(snapshot)
    return result
