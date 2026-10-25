"""Real SQLite identity preservation and explicit rename HTTP boundary."""
import sqlite3
import pytest
from test_learning_library_read_model import library_db, fingerprint, query
from test_learning_library_routes import client
from personal_learning_assistant.services.learning_library_service import LearningLibraryService


def test_rename_persists_searches_and_preserves_source(library_db):
    original = library_db.read_bytes()
    service = LearningLibraryService(database_path=library_db)
    old = next(i.title for i in service.list_items(query()).items if i.key == 'document:d0')
    result = service.rename('document', 'd0', 'Vedic Philosophy — Interactive Notes', expected_title=old)
    assert result['title'] == 'Vedic Philosophy — Interactive Notes'
    fresh = LearningLibraryService(database_path=library_db)
    assert fresh.list_items(query(search='Vedic Philosophy')).items[0].reference.id == 'd0'
    assert library_db.read_bytes() == original
    assert len(fresh.list_items(query(search='MA103N-loose')).items) == 0


def test_grouped_document_name_and_search_metadata(library_db):
    from personal_learning_assistant.repositories.sqlite.search_metadata_repository import SQLiteSearchMetadataRepository
    service = LearningLibraryService(database_path=library_db)
    old = service.resource_detail('r1').documents[0].title
    did = service.resource_detail('r1').documents[0].document_id
    before = fingerprint(library_db)
    service.rename('document', did, 'Friendly title', expected_title=old)
    assert next(d for d in service.resource_detail('r1').documents if d.document_id == did).title == 'Friendly title'
    with sqlite3.connect(library_db) as con:
        meta = SQLiteSearchMetadataRepository(con).document(did)
    assert meta['title'] == 'Friendly title'
    assert meta['version_hash'] == 'a'*64
    assert service.list_items(query(search='Friendly title')).total > 0
    with sqlite3.connect(library_db) as con:
        metadata=SQLiteSearchMetadataRepository(con)
        assert did in metadata.metadata_document_matches(['Friendly title'])
        assert any('Friendly title' in row for row in metadata.metadata_suggestions('Friendly title'))
    assert fingerprint(library_db) == before


@pytest.mark.parametrize('name', ['', '   ', 'x'*161, 'bad\x00name', '<script>', '../path', 'bad\\path', 'bad\u202ename'])
def test_invalid_names_do_not_write(library_db, name):
    s = LearningLibraryService(database_path=library_db)
    with pytest.raises(ValueError):
        s.rename('document', 'd0', name, expected_title='MA103N-loose.pdf')
    assert not library_db.with_name(library_db.name+'.display.sqlite3').exists()


def test_unicode_duplicates_and_conflicting_edit(library_db):
    s = LearningLibraryService(database_path=library_db)
    old = next(i.title for i in s.list_items(query()).items if i.key == 'document:d0')
    assert s.rename('document', 'd0', '  Cafe\u0301 — 章节  ', expected_title=old)['title'] == 'Café — 章节'
    with pytest.raises(ValueError, match='changed'):
        s.rename('document', 'd0', 'Overwrite', expected_title=old)
    first = s.resource_detail('r1').documents[0]
    assert s.rename('document', first.document_id, 'Café — 章节', expected_title=first.title)['duplicate'] is True


def test_duplicate_of_unchanged_title_is_explained(library_db):
    s=LearningLibraryService(database_path=library_db)
    old=next(i.title for i in s.list_items(query()).items if i.key=='document:d0')
    assert s.rename('document','d0','Lecture collection',expected_title=old)['duplicate']


def test_rename_http_guards_and_restart(library_db):
    c = client(library_db)
    page = c.get('/library')
    assert b'library-rename-dialog' in page.data
    token = c.application.extensions['library_rename_csrf']
    s = LearningLibraryService(database_path=library_db)
    old = next(i.title for i in s.list_items(query()).items if i.key == 'document:d0')
    data = {'title':'Readable title','expected_title':old}
    endpoint = '/library/items/document/d0/rename'
    assert c.post(endpoint,json=data).status_code == 403
    headers = {'X-Library-CSRF':token}
    assert c.post(endpoint,json=data,headers={**headers,'Origin':'https://evil.invalid'}).status_code == 403
    assert c.post(endpoint,json=data,headers=headers).status_code == 200
    assert b'Readable title' in client(library_db).get('/library').data
    assert c.get(endpoint).status_code == 405
    assert c.post(endpoint,json=data,headers=headers).status_code == 409


def test_display_store_symlink_is_rejected(library_db, tmp_path):
    from personal_learning_assistant.repositories.sqlite.learning_library_repository import LibraryUnavailableError
    target=tmp_path/'other.sqlite3'; target.write_bytes(b'private')
    try: library_db.with_name(library_db.name+'.display.sqlite3').symlink_to(target)
    except OSError: pytest.skip('Symlinks unavailable on this host')
    with pytest.raises(LibraryUnavailableError):
        LearningLibraryService(database_path=library_db).list_items(query())
    assert target.read_bytes() == b'private'


def test_display_store_wal_reads_fail_closed_without_sidecar_changes(library_db):
    from personal_learning_assistant.repositories.sqlite.learning_library_repository import LibraryUnavailableError
    s=LearningLibraryService(database_path=library_db)
    old=next(i.title for i in s.list_items(query()).items if i.key=='document:d0')
    s.rename('document','d0','Friendly',expected_title=old)
    path=library_db.with_name(library_db.name+'.display.sqlite3')
    with sqlite3.connect(path) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute("UPDATE display_titles SET title='WAL title'")
        writer.commit()
        before={p.name:p.read_bytes() for p in path.parent.glob(path.name+'*')}
        with pytest.raises(LibraryUnavailableError):s.list_items(query())
        assert before=={p.name:p.read_bytes() for p in path.parent.glob(path.name+'*')}
