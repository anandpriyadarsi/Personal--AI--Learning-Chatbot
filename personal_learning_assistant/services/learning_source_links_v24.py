"""Exact source discovery over existing registry and frozen Learning owners.

No index, file search, original-file opener, or persistence belongs to this adapter.
A link certifies a published owner snapshot and current reviewed topic mapping;
it does not independently certify authored content or student mastery.
"""
from pathlib import Path
from urllib.parse import quote
import sqlite3

from personal_learning_assistant.learning_studio.educational_projection import build_preview
from personal_learning_assistant.learning_studio.read_snapshot import frozen_studio
from personal_learning_assistant.learning_studio.validation import HASH, PackageError, identity, integer, require

MAX_MATCHES = 1000


def source_identity(document_id, content_hash):
    identity(document_id)
    require(isinstance(content_hash,str) and HASH.fullmatch(content_hash) is not None,
            'An exact registered source hash is required.')


class LearningSourceLinksV24:
    def __init__(self, evidence, library_database_path, knowledge_database_path,
                 learning_database_path=None):
        self.evidence = evidence
        self.library_database_path = Path(library_database_path)
        self.knowledge_database_path = Path(knowledge_database_path)
        self.learning_database_path = (Path(learning_database_path)
            if learning_database_path is not None else None)

    def _namespace(self):
        try:
            registry = Path(self.evidence.path).resolve()
            require(registry == self.library_database_path.resolve() == self.knowledge_database_path.resolve(),
                    'Source links require the same Academic, Library and Knowledge owner.',503)
            actual = Path(self.evidence.studio.store.path).resolve()
            if self.learning_database_path is not None:
                require(actual == self.learning_database_path.resolve(),
                        'Learning source links require the configured Learning owner.',503)
            require(actual != registry,'Learning and Academic owners must be distinct.',503)
        except (AttributeError, TypeError, ValueError, OSError) as error:
            raise PackageError('Source owner configuration is unavailable.',503) from error

    def project(self, document_id, content_hash, *, offset=0, limit=10):
        source_identity(document_id,content_hash)
        integer(offset,0,MAX_MATCHES);integer(limit,1,20)
        self._namespace()
        try:
            # Visibility, exact source revision and catalogue share ONE registry
            # transaction from the evidence owner's authorized RAM snapshot.
            with self.evidence._connection() as con:
                row=con.execute('''SELECT d.id,d.content_hash,d.mime_type
                    FROM knowledge_documents d WHERE d.id=? AND (
                    NOT EXISTS(SELECT 1 FROM resource_documents rd WHERE rd.document_id=d.id)
                    OR EXISTS(SELECT 1 FROM resource_documents rd JOIN resources r ON r.id=rd.resource_id
                        WHERE rd.document_id=d.id AND r.archived_at IS NULL AND r.deleted_at IS NULL))''',
                    (document_id,)).fetchone()
                require(row is not None,'Registered source is unavailable.',404)
                require(row['mime_type']=='application/pdf','Source links require a registered PDF.',404)
                require(row['content_hash']==content_hash,'Registered source changed. Reload its current source view.',409)
                catalogue=self.evidence._catalogue(con)
            # One captured Learning image backs every candidate in this response.
            frozen=frozen_studio(self.evidence.studio,catalogue=catalogue)
            with frozen.store.connection() as con:
                matches=[dict(r) for r in con.execute('''SELECT m.module_id,m.revision
                    FROM active_modules a JOIN modules m USING(module_id,revision)
                    JOIN publications p USING(module_id,revision)
                    WHERE json_extract(m.package_json,'$.source.source_id')=?
                      AND json_extract(m.package_json,'$.source.sha256')=?
                    ORDER BY m.module_id,m.revision LIMIT ?''',
                    (document_id,content_hash,MAX_MATCHES+1))]
            require(len(matches)<=MAX_MATCHES,'Source lesson inventory exceeds its safe bound.',503)
            lessons=[];blocked=0
            for match in matches:
                try:
                    # build_preview reuses the frozen payload; it never recaptures
                    # a live store or invokes the original-file source loader.
                    preview=build_preview(frozen,match['module_id'],match['revision'],
                        catalogue=catalogue,as_of=self.evidence.now())
                    require(preview['source']['source_id']==document_id and
                            preview['source']['sha256']==content_hash and
                            preview['source']['media_type']=='application/pdf',
                            'Published source identity changed.',409)
                    require(preview['mapping_status']=='reviewed_current_catalogue',
                            'Current reviewed topic mapping is required.',409)
                except PackageError:
                    blocked+=1
                    continue
                mid=preview['module']['id'];revision=preview['module']['revision']
                target=quote(mid,safe='')+'/'+str(revision)
                lessons.append({'module_id':mid,'revision':revision,'title':preview['module']['title'],
                    'lesson_url':'/learning/modules/'+target+'?view=learn',
                    'evidence_url':'/academic-evidence/learning/'+target,
                    'mapping_status':preview['mapping_status'],
                    'source_status':'published_snapshot_validated',
                    'semantic_review':preview['semantic_review']})
            return {'schema':'anvaya.learning-source-links.v1','state':'available' if lessons else 'empty',
                'document_id':document_id,'content_hash':content_hash,
                'lessons':lessons[offset:offset+limit],'offset':offset,'limit':limit,
                'has_more':offset+limit<len(lessons),'blocked_matches':blocked}
        except sqlite3.Error as error:
            raise PackageError('Source links are unavailable. Existing records were not changed.',503) from error
