import json
import sqlite3
from io import BytesIO
import pytest
from personal_learning_assistant.ingestion.extractors import TranscriptExtractor, ExtractionError


def test_source_identity_is_placement_and_revision_bound():
    from personal_learning_assistant.domain.multimodal_models import source_ref, validate_locator
    doc=dict(id='one',sha256='a'*64,generation=2,metadata_revision=3,subject_id='math')
    assert source_ref(doc)!=source_ref(dict(doc,id='two'))
    assert source_ref(doc)!=source_ref(dict(doc,metadata_revision=4))
    assert validate_locator({'kind':'pdf_page','page':1})['schema_version']==2


@pytest.mark.parametrize('locator',[
    {'kind':'pdf_page','page':0}, {'kind':'pdf_page','page':True},
    {'kind':'image','bbox':[0,0,2,1]}, {'kind':'transcript_cue','start_ms':10,'end_ms':10},
    {'kind':'transcript_cue','start_ms':float('nan'),'end_ms':200},
    {'kind':'image','schema_version':999}, {'kind':'image','path':'/etc/passwd'},
])
def test_invalid_locator_fails_closed(locator):
    from personal_learning_assistant.domain.multimodal_models import validate_locator
    with pytest.raises(ValueError):validate_locator(locator)


@pytest.mark.parametrize('timing',['00:61.000 --> 00:62.000','x00:01.000 --> 00:02.000','00:02.000 --> 00:02.000'])
def test_transcript_rejects_invalid_times(timing):
    with pytest.raises(ExtractionError):TranscriptExtractor().extract((timing+'\ntext').encode(),source_name='a.vtt')


def test_transcript_rejects_backwards_cues_and_bounds():
    with pytest.raises(ExtractionError):
        TranscriptExtractor().extract(b'00:02.000 --> 00:03.000\na\n\n00:01.000 --> 00:02.000\nb',source_name='a.vtt')
    with pytest.raises(ExtractionError):TranscriptExtractor().extract(b'a'*1_048_577,source_name='a.srt')


def test_explicit_activation_backups_restore_and_idempotence(tmp_path):
    from personal_learning_assistant.services.multimodal_schema import activate
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    db=tmp_path/'data/learning_assistant.db';db.parent.mkdir();apply_migrations(db)
    lib=NativeDocumentLibrary(db.parent/'native_library',autostart=False)
    doc=lib.upload(BytesIO(b'unchanged'),'a.txt',indexing=False)
    dry=activate(db,lib.root,apply=False)
    assert dry['pending'] and not list(lib.root.glob('mm*'))
    result=activate(db,lib.root,apply=True)
    backup=result['backup'];assert (backup/'native/blobs'/doc['sha256']).read_bytes()==b'unchanged'
    with sqlite3.connect(backup/'academic.sqlite3') as con:assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not activate(db,lib.root,apply=True)['pending']
    # Old native reader accepts additive tables with schema version unchanged.
    clone=NativeDocumentLibrary(lib.root,autostart=False);assert clone.original(doc['id']).read_bytes()==b'unchanged';clone.close();lib.close()
    with pytest.raises(ValueError):activate(tmp_path/'missing.db',lib.root,apply=True)


def test_scoped_budget_revocation_and_unknown_outcome(tmp_path):
    from personal_learning_assistant.services.multimodal_schema import NATIVE_SQL
    from personal_learning_assistant.services.provider_permission_service import PermissionGuard
    db=tmp_path/'permissions.db'
    with sqlite3.connect(db) as con:con.executescript(NATIVE_SQL)
    guard=PermissionGuard(db,monthly_limit_micros=100)
    scope={'owner':'native_library','document_id':'one','hash':'a'*64,'generation':1,'revision':1}
    with pytest.raises(ValueError):guard.reserve('missing',scope,'provider','answer','request0',20)
    receipt=guard.grant(scope,'provider','answer',max_cost_micros=30)
    guard.reserve(receipt,scope,'provider','answer','request1',30)
    with pytest.raises(ValueError):guard.reserve(receipt,dict(scope,document_id='two'),'provider','answer','request2',20)
    guard.finish('request1','outcome_unknown')
    with pytest.raises(ValueError):guard.reserve(receipt,scope,'provider','answer','request1',30)
    guard.revoke(receipt)
    with pytest.raises(ValueError):guard.reserve(receipt,scope,'provider','answer','request3',30)
    zero=PermissionGuard(db,monthly_limit_micros=0)
    receipt=zero.grant(scope,'provider','answer',max_cost_micros=30)
    with pytest.raises(ValueError):zero.reserve(receipt,scope,'provider','answer','request4',1)


def test_activation_refuses_nested_symlinks_before_copying(tmp_path):
    from personal_learning_assistant.services.multimodal_schema import activate
    from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    db=tmp_path/'data/academic.db';db.parent.mkdir();apply_migrations(db)
    lib=NativeDocumentLibrary(db.parent/'native_library',autostart=False)
    secret=tmp_path/'outside.txt';secret.write_text('not an owner asset')
    (lib.root/'blobs'/'symlink').symlink_to(secret)
    with pytest.raises(ValueError):activate(db,lib.root,apply=True)
    assert not any(p.read_bytes()==b'not an owner asset' for p in (db.parent/'backups').rglob('outside.txt'))
    lib.close()
