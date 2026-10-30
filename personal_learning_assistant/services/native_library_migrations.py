"""Additive migration of the native owner's metadata, never academic tables."""
from contextlib import closing
import sqlite3

SCHEMA_VERSION = 2


def migrate(library, previous_version):
    if previous_version == 2:
        with library.connection() as con:
            if 'scope_override' in {r[1] for r in con.execute('PRAGMA table_info(documents)')}:return
    # Backup precedes the first schema-2 write. Its destination is outside data.
    if previous_version == 1:
        from personal_learning_assistant.android_backup import export_backup_file
        if library.root.name == 'native_library' and library.root.parent.name == 'data':
            export_backup_file(library.root.parent.parent)
        else:
            # Standalone callers own only the native store; preserve an exact
            # consistent v1 SQLite snapshot next to it before additive migration.
            with closing(sqlite3.connect(str(library.database))) as source:
                with closing(sqlite3.connect(str(library.root/'pre-v2.sqlite3'))) as target:
                    source.backup(target)
    with library.connection(write=True) as con:
        for table, columns in {
            'folders': [('binding_id','TEXT'),('node_kind',"TEXT NOT NULL DEFAULT 'folder'"),
                        ('sort_order','INTEGER NOT NULL DEFAULT 0'),('template_origin','TEXT')],
            'documents': [('scope_override','INTEGER NOT NULL DEFAULT 0'),('managed_original','TEXT'),('favorite','INTEGER NOT NULL DEFAULT 0'),('opened_at','TEXT'),
                          ('trashed_at','TEXT'),('availability',"TEXT NOT NULL DEFAULT 'available'"),
                          ('metadata_revision','INTEGER NOT NULL DEFAULT 1'),('tutor_state',"TEXT NOT NULL DEFAULT 'preparing'")]
        }.items():
            present={r[1] for r in con.execute('PRAGMA table_info('+table+')')}
            for name,definition in columns:
                if name not in present: con.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
        statements = [
            '''CREATE TABLE IF NOT EXISTS semesters(id TEXT PRIMARY KEY,number INTEGER NOT NULL,
                 label TEXT NOT NULL,year TEXT,program TEXT,folder_id TEXT NOT NULL UNIQUE REFERENCES folders(id),
                 sort_order INTEGER NOT NULL DEFAULT 0)''',
            '''CREATE TABLE IF NOT EXISTS subject_bindings(id TEXT PRIMARY KEY,semester_id TEXT NOT NULL REFERENCES semesters(id),
                 authority TEXT NOT NULL,course_id TEXT NOT NULL,code TEXT NOT NULL,folder_id TEXT NOT NULL UNIQUE REFERENCES folders(id),
                 UNIQUE(semester_id,authority,course_id))''',
            '''CREATE TABLE IF NOT EXISTS source_links(document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                 namespace TEXT NOT NULL,source_id TEXT NOT NULL,content_hash TEXT NOT NULL,state TEXT NOT NULL,
                 operation_id TEXT NOT NULL,PRIMARY KEY(document_id,namespace,source_id))''',
            '''CREATE TABLE IF NOT EXISTS source_pins(document_id TEXT NOT NULL REFERENCES documents(id),
                 owner TEXT NOT NULL,reference_id TEXT NOT NULL,PRIMARY KEY(document_id,owner,reference_id))''',
            '''CREATE TABLE IF NOT EXISTS processing_jobs(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                 content_hash TEXT NOT NULL,generation INTEGER NOT NULL,extraction_version TEXT NOT NULL,
                 state TEXT NOT NULL DEFAULT 'pending',lease_owner TEXT,lease_until REAL,attempts INTEGER NOT NULL DEFAULT 0,
                 checkpoint TEXT NOT NULL DEFAULT 'saved',error_code TEXT NOT NULL DEFAULT '',
                 UNIQUE(document_id,generation,extraction_version))''',
            '''CREATE TABLE IF NOT EXISTS template_applications(folder_id TEXT NOT NULL REFERENCES folders(id),
                 template_key TEXT NOT NULL,origin_key TEXT NOT NULL,child_id TEXT,version INTEGER NOT NULL,
                 PRIMARY KEY(folder_id,template_key,origin_key))''',
            '''CREATE TABLE IF NOT EXISTS migration_ledger(operation_id TEXT PRIMARY KEY,phase TEXT NOT NULL,
                 completed_at TEXT NOT NULL,details TEXT NOT NULL DEFAULT '{}')''',
            'CREATE INDEX IF NOT EXISTS document_lifecycle ON documents(trashed_at,folder_id)',
            'CREATE INDEX IF NOT EXISTS job_queue ON processing_jobs(state,lease_until)',
        ]
        for statement in statements: con.execute(statement)
        con.execute("INSERT OR IGNORE INTO migration_ledger VALUES('native-schema-v2','complete',datetime('now'),'{}')")
        con.execute('PRAGMA user_version=2')


def validate_schema(con):
    """Prove the restored owner can reopen, not just SQLite file integrity."""
    version=con.execute('PRAGMA user_version').fetchone()[0]
    if version not in (1,2):raise ValueError('Unsupported native Library schema')
    required={
        'folders':{'id','name','parent_id'},
        'documents':{'id','original_name','display_name','kind','sha256','size','folder_id','subject_id','topic','tags',
                     'indexing_enabled','ocr','generation','status','status_detail','position_count','indexed_count','created_at','updated_at'},
        'pages':{'id','document_id','position','text'},
    }
    if version==2:
        required['folders']|={'binding_id','node_kind','sort_order','template_origin'}
        required['documents']|={'scope_override','managed_original','favorite','opened_at','trashed_at','availability','metadata_revision','tutor_state'}
        required.update({
            'semesters':{'id','number','label','year','program','folder_id','sort_order'},
            'subject_bindings':{'id','semester_id','authority','course_id','code','folder_id'},
            'source_links':{'document_id','namespace','source_id','content_hash','state','operation_id'},
            'source_pins':{'document_id','owner','reference_id'},
            'processing_jobs':{'id','document_id','content_hash','generation','extraction_version','state','lease_owner','lease_until','attempts','checkpoint','error_code'},
            'template_applications':{'folder_id','template_key','origin_key','child_id','version'},
            'migration_ledger':{'operation_id','phase','completed_at','details'},
        })
    for table,columns in required.items():
        if not columns<={r[1] for r in con.execute('PRAGMA table_info('+table+')')}:
            raise ValueError('Incompatible native Library owner schema')
