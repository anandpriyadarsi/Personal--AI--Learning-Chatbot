"""Test-only, scoped academic data. Never read a source-root database or vault."""
from pathlib import Path
import sqlite3


NOW = '2026-10-01T00:30:00Z'


def build_academic_database(directory: Path) -> Path:
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.domain.tutor_models import TutorSessionSpec
    from personal_learning_assistant.repositories.sqlite.tutor_repository import SQLiteTutorRepository
    from personal_learning_assistant.services.tutor_session_service import TutorSessionService

    path = directory / 'learning_assistant.db'
    if path.exists() or path.is_symlink():
        raise FileExistsError('Synthetic fixture must use a new database')
    apply_migrations(path)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute("INSERT INTO courses(id,code,name,status,created_at,updated_at) VALUES('synthetic-ma','MA103N','Synthetic Linear Algebra','active',?,?)", (NOW, NOW))
        connection.execute("INSERT INTO topics(id,course_id,name,normalized_name,position,status,created_at,updated_at) VALUES('synthetic-rank','synthetic-ma','Matrix Rank','matrix rank',1,'not_started',?,?)", (NOW, NOW))
        connection.execute("INSERT INTO knowledge_documents(id,kind,path_key,mime_type,content_hash,size_bytes,extraction_status,extraction_version,created_at,updated_at) VALUES('synthetic-doc','document','synthetic/grounding.txt','text/plain','fixture-hash',60,'completed','fixture-v1',?,?)", (NOW, NOW))
        connection.execute("INSERT INTO knowledge_chunks(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,text_hash,extraction_version,chunk_text) VALUES('synthetic-chunk','synthetic-doc',0,1,0,60,'text','fixture-chunk','fixture-v1','The rank is the number of pivots in a row echelon matrix.')")
        TutorSessionService(SQLiteTutorRepository(connection), now=lambda: NOW,
                            id_factory=lambda prefix: 'synthetic-tutor-session').create_session(
            TutorSessionSpec(mode='concept', source_policy='source_only', course_id='synthetic-ma', title='Synthetic reopen session'))
    finally:
        connection.close()
    return path
