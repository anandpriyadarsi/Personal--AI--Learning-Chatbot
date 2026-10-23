"""Registered-source reads must release actual SQLite file handles immediately."""
from contextlib import closing
import hashlib
import sqlite3
import pytest
from personal_learning_assistant.learning_studio.sources import RegisteredSources
from personal_learning_assistant.learning_studio.validation import PackageError


@pytest.mark.parametrize('known',[True,False])
def test_registered_source_connection_closed_on_success_and_rejection(tmp_path,monkeypatch,known):
    path=tmp_path/'registry.db'; documents=tmp_path/'documents';documents.mkdir()
    raw=b'%PDF-synthetic-lifecycle';(documents/'source.pdf').write_bytes(raw)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('CREATE TABLE knowledge_documents(id TEXT,path_key TEXT,content_hash TEXT,mime_type TEXT)')
        db.execute('INSERT INTO knowledge_documents VALUES(?,?,?,?)',
            ('source','documents/source.pdf',hashlib.sha256(raw).hexdigest(),'application/pdf'))
    connect=sqlite3.connect; handles=[]
    def tracked(*args,**kwargs):
        con=connect(*args,**kwargs);handles.append(con);return con
    monkeypatch.setattr(sqlite3,'connect',tracked)
    reader=RegisteredSources(path,{'documents':documents})
    if known: assert reader('source')==raw
    else:
        with pytest.raises(PackageError):reader('missing')
    assert len(handles)==1
    with pytest.raises(sqlite3.ProgrammingError,match='closed'):
        handles[0].execute('SELECT 1')
