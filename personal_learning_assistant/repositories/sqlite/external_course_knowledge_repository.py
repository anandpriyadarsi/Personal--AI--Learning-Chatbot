"""SQLite adapter for Phase 5.7 external-course package projection.

No new schema is introduced. External courses and lectures are Resources 2
objects; the package is registered in knowledge_documents/knowledge_chunks.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections import defaultdict
from typing import Dict, Mapping, Optional, Sequence, Tuple

from personal_learning_assistant.domain.external_course_crosswalk_models import TopicCatalogEntry
from personal_learning_assistant.ingestion.chunking import encode_chunk_type
from personal_learning_assistant.repositories.sqlite.connection import transaction


class ExternalCourseKnowledgeRepositoryError(RuntimeError):
    pass


class ExternalCourseKnowledgeConflictError(ExternalCourseKnowledgeRepositoryError):
    pass


class ExternalCourseKnowledgeSchemaError(ExternalCourseKnowledgeRepositoryError):
    pass


_RESOURCE_NAMESPACE = uuid.UUID("b4b1fa48-70f2-4312-826c-a0cc4a73da79")
_KNOWLEDGE_NAMESPACE = uuid.UUID("e3334c65-5cc2-4c52-bd02-94fcba153aea")
_CHUNK_NAMESPACE = uuid.UUID("af1600bd-98f9-4b14-a1bd-47bf33882ba3")
_JOB_NAMESPACE = uuid.UUID("d4128d1d-3b44-4a65-a6df-58977f5dbe3b")

_REQUIRED = {
    "courses": {"id", "code"},
    "topics": {"id", "course_id", "name", "normalized_name", "deleted_at"},
    "topic_aliases": {"topic_id", "course_id", "normalized_alias"},
    "resources": {
        "id", "resource_type", "title", "canonical_uri", "provider",
        "external_id", "status", "created_at", "updated_at", "deleted_at",
    },
    "resource_courses": {"resource_id", "course_id", "role"},
    "resource_topics": {
        "resource_id", "topic_id", "relation_source", "confidence",
    },
    "knowledge_documents": {
        "id", "kind", "canonical_uri", "path_key", "mime_type", "content_hash",
        "size_bytes", "extraction_status", "extraction_version",
        "extraction_error", "created_at", "updated_at",
    },
    "resource_documents": {"resource_id", "document_id", "role"},
    "knowledge_chunks": {
        "id", "document_id", "ordinal", "page_number", "char_start", "char_end",
        "chunk_type", "text_hash", "extraction_version", "chunk_text",
    },
    "index_jobs": {
        "id", "document_id", "content_hash", "index_kind", "model_name",
        "model_version", "index_version", "status", "created_at", "error",
    },
    "outbox_events": {
        "id", "event_type", "entity_type", "entity_id", "payload_json",
        "created_at", "processed_at", "failed_at", "error", "attempts",
    },
}


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _stable(namespace, label: str) -> str:
    return str(uuid.uuid5(namespace, label))


def resource_external_id(course_id: str, lecture_number: Optional[str] = None) -> str:
    if lecture_number is None:
        return course_id
    return "{}:lecture:{}".format(course_id, lecture_number)


def stable_resource_id(course_id: str, lecture_number: Optional[str] = None) -> str:
    return _stable(
        _RESOURCE_NAMESPACE,
        "external-resource|" + resource_external_id(course_id, lecture_number),
    )


def stable_document_id(kind: str, path_key: str) -> str:
    return _stable(
        _KNOWLEDGE_NAMESPACE,
        "knowledge-document|{}|path:{}".format(kind, path_key),
    )


class SQLiteExternalCourseKnowledgeRepository:
    def __init__(self, connection: sqlite3.Connection, *, validate_schema: bool = True):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        if validate_schema:
            self.validate_schema()

    def validate_schema(self):
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing_tables = sorted(set(_REQUIRED) - tables)
        if missing_tables:
            raise ExternalCourseKnowledgeSchemaError(
                "required Phase 5.7 tables missing: {}".format(
                    ", ".join(missing_tables)
                )
            )
        issues = []
        for table, required in _REQUIRED.items():
            columns = {
                str(row[1])
                for row in self.connection.execute(
                    'PRAGMA table_info("{}")'.format(table)
                )
            }
            missing = sorted(required - columns)
            if missing:
                issues.append("{}:[{}]".format(table, ",".join(missing)))
        if issues:
            raise ExternalCourseKnowledgeSchemaError(
                "Phase 5.7 schema is incomplete: {}".format("; ".join(issues))
            )

    def course_id_for_code(self, code: str) -> str:
        rows = self.connection.execute(
            "SELECT id FROM courses WHERE lower(code)=lower(?) AND deleted_at IS NULL",
            (str(code),),
        ).fetchall()
        if len(rows) != 1:
            raise ExternalCourseKnowledgeConflictError(
                "expected exactly one active local course for code {}".format(code)
            )
        return str(rows[0][0])

    def topic_index(self, course_id: str) -> Dict[str, Tuple[str, ...]]:
        candidates = defaultdict(set)
        for row in self.connection.execute(
            "SELECT id,name,normalized_name FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL",
            (course_id,),
        ):
            topic_id = str(row[0])
            candidates[_normalize(row[1])].add(topic_id)
            candidates[_normalize(row[2])].add(topic_id)
        for row in self.connection.execute(
            "SELECT topic_id,normalized_alias FROM topic_aliases WHERE course_id=?",
            (course_id,),
        ):
            candidates[_normalize(row[1])].add(str(row[0]))
        return {
            label: tuple(sorted(values))
            for label, values in candidates.items()
            if label
        }

    def topic_catalog(self, course_id: str) -> Tuple[TopicCatalogEntry, ...]:
        aliases = defaultdict(list)
        for row in self.connection.execute(
            "SELECT topic_id,alias FROM topic_aliases WHERE course_id=? "
            "ORDER BY normalized_alias,alias",
            (course_id,),
        ):
            aliases[str(row[0])].append(str(row[1]))
        rows = self.connection.execute(
            "SELECT id,name,normalized_name FROM topics "
            "WHERE course_id=? AND deleted_at IS NULL "
            "ORDER BY position,name,id",
            (course_id,),
        ).fetchall()
        return tuple(
            TopicCatalogEntry(
                topic_id=str(row["id"]),
                name=str(row["name"]),
                normalized_name=str(row["normalized_name"]),
                aliases=tuple(aliases.get(str(row["id"]), ())),
            )
            for row in rows
        )

    def find_resource_by_external_identity(
        self, provider: str, external_id: str
    ) -> Optional[str]:
        rows = self.connection.execute(
            "SELECT id FROM resources WHERE lower(provider)=lower(?) "
            "AND external_id=? AND deleted_at IS NULL",
            (provider, external_id),
        ).fetchall()
        if len(rows) > 1:
            raise ExternalCourseKnowledgeConflictError(
                "provider/external identity resolves to multiple resources"
            )
        return None if not rows else str(rows[0][0])

    def find_document_by_path(self, path_key: str) -> Optional[str]:
        rows = self.connection.execute(
            "SELECT id FROM knowledge_documents WHERE path_key=?",
            (path_key,),
        ).fetchall()
        if len(rows) > 1:
            raise ExternalCourseKnowledgeConflictError(
                "portable package path resolves to multiple knowledge documents"
            )
        return None if not rows else str(rows[0][0])

    def extraction_is_current(
        self, document_id: str, extraction_version: str, expected_chunks: int
    ) -> bool:
        row = self.connection.execute(
            "SELECT extraction_status,extraction_version FROM knowledge_documents "
            "WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            return False
        if str(row[0]) != "completed" or str(row[1]) != extraction_version:
            return False
        count = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_id=? AND extraction_version=?",
                (document_id, extraction_version),
            ).fetchone()[0]
        )
        return count == int(expected_chunks)

    def apply_package(
        self,
        *,
        package,
        package_key: str,
        local_course_id: str,
        lecture_topic_ids: Mapping[str, Sequence[str]],
        course_topic_ids: Sequence[str],
        label_topic_ids: Mapping[str, str],
        crosswalk_sha256: str,
        now: str,
        extraction_version: str,
        handoff_index_version: str,
    ):
        provider = "mit_ocw"
        course_external_id = resource_external_id(package.course_id)
        course_resource_id = (
            self.find_resource_by_external_identity(provider, course_external_id)
            or stable_resource_id(package.course_id)
        )
        hubs = dict(package.official_hubs)
        course_url = str(hubs.get("course") or "").strip()
        if not course_url:
            raise ExternalCourseKnowledgeConflictError(
                "MIT course canonical URL is missing from package manifest"
            )

        documents = (
            (
                "external_course_manifest",
                "{}/course_manifest.json".format(package_key),
                package.manifest_sha256,
                package.manifest_size,
                "application/json",
            ),
            (
                "external_course_inventory",
                "{}/lecture_inventory.json".format(package_key),
                package.inventory_sha256,
                package.inventory_size,
                "application/json",
            ),
            (
                "external_course_schema",
                "{}/schema.json".format(package_key),
                package.schema_sha256,
                package.schema_size,
                "application/schema+json",
            ),
            (
                "external_course_chunks",
                "{}/chunks.jsonl".format(package_key),
                package.chunks_sha256,
                package.chunks_size,
                "application/x-ndjson",
            ),
        )

        resolved_documents = {}
        with transaction(self.connection, immediate=True):
            self._upsert_resource(
                resource_id=course_resource_id,
                resource_type="external_course",
                title=package.course_title,
                canonical_uri=course_url,
                provider=provider,
                external_id=course_external_id,
                now=now,
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO resource_courses(resource_id,course_id,role) "
                "VALUES (?,?,'external_course')",
                (course_resource_id, local_course_id),
            )

            for topic_id in sorted(set(course_topic_ids)):
                self.connection.execute(
                    "INSERT OR IGNORE INTO resource_topics"
                    "(resource_id,topic_id,relation_source,confidence) "
                    "VALUES (?,?,'imported',1.0)",
                    (course_resource_id, topic_id),
                )

            for kind, path_key, content_hash, size_bytes, mime_type in documents:
                existing = self.find_document_by_path(path_key)
                document_id = existing or stable_document_id(kind, path_key)
                resolved_documents[kind] = document_id
                self._upsert_document(
                    document_id=document_id,
                    kind=kind,
                    path_key=path_key,
                    mime_type=mime_type,
                    content_hash=content_hash,
                    size_bytes=size_bytes,
                    now=now,
                    reset_extraction=(kind == "external_course_chunks"),
                )
                role = "source" if kind == "external_course_chunks" else "metadata_package"
                self.connection.execute(
                    "INSERT OR IGNORE INTO resource_documents(resource_id,document_id,role) "
                    "VALUES (?,?,?)",
                    (course_resource_id, document_id, role),
                )

            lecture_resource_ids = {}
            inventory_document_id = resolved_documents["external_course_inventory"]
            chunks_document_id = resolved_documents["external_course_chunks"]
            for lecture in package.lectures:
                ext_id = resource_external_id(package.course_id, lecture.lecture_number)
                resource_id = (
                    self.find_resource_by_external_identity(provider, ext_id)
                    or stable_resource_id(package.course_id, lecture.lecture_number)
                )
                lecture_resource_ids[lecture.lecture_number] = resource_id
                self._upsert_resource(
                    resource_id=resource_id,
                    resource_type="external_lecture",
                    title="MIT 18.06 L{} — {}".format(
                        lecture.lecture_number, lecture.lecture_title
                    ),
                    canonical_uri=lecture.official_lecture_url,
                    provider=provider,
                    external_id=ext_id,
                    now=now,
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO resource_courses(resource_id,course_id,role) "
                    "VALUES (?,?,'supporting')",
                    (resource_id, local_course_id),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO resource_documents(resource_id,document_id,role) "
                    "VALUES (?,?,'metadata_package')",
                    (resource_id, inventory_document_id),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO resource_documents(resource_id,document_id,role) "
                    "VALUES (?,?,'source')",
                    (resource_id, chunks_document_id),
                )
                for topic_id in sorted(set(lecture_topic_ids.get(lecture.lecture_number, ()))):
                    self.connection.execute(
                        "INSERT OR IGNORE INTO resource_topics"
                        "(resource_id,topic_id,relation_source,confidence) "
                        "VALUES (?,?,'imported',1.0)",
                        (resource_id, topic_id),
                    )

            self.connection.execute(
                "DELETE FROM knowledge_chunks "
                "WHERE document_id=? AND extraction_version=?",
                (chunks_document_id, extraction_version),
            )
            for ordinal, chunk in enumerate(package.chunks):
                locator = {
                    "external_course_id": package.course_id,
                    "package_version": package.version,
                    "package_chunk_id": chunk.chunk_id,
                    "lecture_number": chunk.lecture_number,
                    "lecture_numbers": list(chunk.lecture_numbers),
                    "lecture_title": chunk.lecture_title,
                    "topic": chunk.topic,
                    "concepts": list(chunk.concepts),
                    "prerequisites": list(chunk.prerequisites),
                    "related_concepts": list(chunk.related_concepts),
                    "nitk_weeks": list(chunk.nitk_weeks),
                    "priority": chunk.priority,
                    "source": dict(chunk.source),
                    "source_url": chunk.source_url,
                    "supporting_source_urls": list(chunk.supporting_source_urls),
                    "retrieval_queries": list(chunk.retrieval_queries),
                    "answer_modes": list(chunk.answer_modes),
                    "content_version": chunk.content_version,
                    "crosswalk_sha256": crosswalk_sha256,
                    "local_topic_ids": sorted(
                        {
                            label_topic_ids[key]
                            for key in (
                                _normalize(chunk.topic),
                                *(_normalize(item) for item in chunk.concepts),
                            )
                            if key in label_topic_ids
                        }
                    ),
                    "local_prerequisite_topic_ids": sorted(
                        {
                            label_topic_ids[_normalize(item)]
                            for item in chunk.prerequisites
                            if _normalize(item) in label_topic_ids
                        }
                    ),
                    "local_related_topic_ids": sorted(
                        {
                            label_topic_ids[_normalize(item)]
                            for item in chunk.related_concepts
                            if _normalize(item) in label_topic_ids
                        }
                    ),
                }
                chunk_id = _stable(
                    _CHUNK_NAMESPACE,
                    "external-chunk|{}|{}|{}".format(
                        package.course_id,
                        extraction_version,
                        chunk.chunk_id,
                    ),
                )
                self.connection.execute(
                    "INSERT INTO knowledge_chunks "
                    "(id,document_id,ordinal,page_number,char_start,char_end,chunk_type,"
                    "text_hash,extraction_version,chunk_text) "
                    "VALUES (?,?,?,NULL,0,?,?,?,?,?)",
                    (
                        chunk_id,
                        chunks_document_id,
                        ordinal,
                        len(chunk.text),
                        encode_chunk_type(chunk.chunk_type, locator),
                        chunk.content_hash,
                        extraction_version,
                        chunk.text,
                    ),
                )

            self.connection.execute(
                "UPDATE knowledge_documents SET extraction_status='completed',"
                "extraction_version=?,extraction_error=NULL,updated_at=? WHERE id=?",
                (extraction_version, now, chunks_document_id),
            )
            self.connection.execute(
                "UPDATE index_jobs SET status='stale',error=? "
                "WHERE document_id=? AND content_hash<>? "
                "AND status IN ('pending','running','completed')",
                (
                    "superseded by current external-course package",
                    chunks_document_id,
                    package.chunks_sha256,
                ),
            )
            self.connection.execute(
                "UPDATE index_jobs SET status='stale',error=? "
                "WHERE document_id=? AND content_hash=? "
                "AND index_kind='retrieval_handoff' "
                "AND index_version<>? "
                "AND status IN ('pending','running','completed')",
                (
                    "superseded by reviewed topic crosswalk",
                    chunks_document_id,
                    package.chunks_sha256,
                    handoff_index_version,
                ),
            )
            job_id = _stable(
                _JOB_NAMESPACE,
                "external-handoff|{}|{}|{}".format(
                    chunks_document_id,
                    package.chunks_sha256,
                    handoff_index_version,
                ),
            )
            existing_job = self.connection.execute(
                "SELECT id FROM index_jobs WHERE document_id=? AND content_hash=? "
                "AND index_kind='retrieval_handoff' AND model_name='' AND model_version='' "
                "AND index_version=?",
                (
                    chunks_document_id,
                    package.chunks_sha256,
                    handoff_index_version,
                ),
            ).fetchone()
            if existing_job is None:
                self.connection.execute(
                    "INSERT INTO index_jobs "
                    "(id,document_id,content_hash,index_kind,model_name,model_version,"
                    "index_version,status,created_at,started_at,completed_at,failed_at,error) "
                    "VALUES (?,?,?,'retrieval_handoff','','',?,'pending',?,"
                    "NULL,NULL,NULL,NULL)",
                    (
                        job_id,
                        chunks_document_id,
                        package.chunks_sha256,
                        handoff_index_version,
                        now,
                    ),
                )
            else:
                job_id = str(existing_job[0])

            event_id = _stable(
                _JOB_NAMESPACE,
                "external-course-outbox|{}|{}".format(
                    package.course_id, package.chunks_sha256
                ),
            )
            payload = json.dumps(
                {
                    "course_id": package.course_id,
                    "package_version": package.version,
                    "lecture_count": len(package.lectures),
                    "chunk_count": len(package.chunks),
                    "chunks_document_id": chunks_document_id,
                    "handoff_job_id": job_id,
                    "crosswalk_sha256": crosswalk_sha256,
                    "mapped_topic_id_count": len(set(label_topic_ids.values())),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO outbox_events "
                "(id,event_type,entity_type,entity_id,payload_json,created_at,"
                "processed_at,failed_at,error,attempts) "
                "VALUES (?,'knowledge.external_course.ingested','resource',?,?,?,"
                "NULL,NULL,NULL,0)",
                (event_id, course_resource_id, payload, now),
            )

        return {
            "course_resource_id": course_resource_id,
            "lecture_resource_ids": lecture_resource_ids,
            "document_ids": resolved_documents,
            "chunks_document_id": resolved_documents["external_course_chunks"],
            "handoff_job_id": job_id,
        }

    def _upsert_resource(
        self,
        *,
        resource_id: str,
        resource_type: str,
        title: str,
        canonical_uri: str,
        provider: str,
        external_id: str,
        now: str,
    ):
        existing = self.connection.execute(
            "SELECT id,provider,external_id FROM resources WHERE id=?",
            (resource_id,),
        ).fetchone()
        if existing is None:
            self.connection.execute(
                "INSERT INTO resources "
                "(id,resource_type,title,canonical_uri,provider,external_id,status,"
                "rating,quality_note,created_at,updated_at,completed_at,archived_at,deleted_at) "
                "VALUES (?,?,?,?,?,?,'not_started',NULL,'',?,?,NULL,NULL,NULL)",
                (
                    resource_id,
                    resource_type,
                    title,
                    canonical_uri,
                    provider,
                    external_id,
                    now,
                    now,
                ),
            )
            return
        if (
            str(existing["provider"]).casefold() != provider.casefold()
            or str(existing["external_id"]) != external_id
        ):
            raise ExternalCourseKnowledgeConflictError(
                "stable resource ID is already owned by a different external identity"
            )
        self.connection.execute(
            "UPDATE resources SET resource_type=?,title=?,canonical_uri=?,updated_at=? "
            "WHERE id=?",
            (resource_type, title, canonical_uri, now, resource_id),
        )

    def _upsert_document(
        self,
        *,
        document_id: str,
        kind: str,
        path_key: str,
        mime_type: str,
        content_hash: str,
        size_bytes: int,
        now: str,
        reset_extraction: bool,
    ):
        row = self.connection.execute(
            "SELECT id,kind,path_key,content_hash FROM knowledge_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            self.connection.execute(
                "INSERT INTO knowledge_documents "
                "(id,kind,canonical_uri,path_key,mime_type,content_hash,size_bytes,"
                "source_timestamp,extraction_status,extraction_version,"
                "extraction_error,created_at,updated_at) "
                "VALUES (?,?,NULL,?,?,?,?,NULL,'pending','',NULL,?,?)",
                (
                    document_id,
                    kind,
                    path_key,
                    mime_type,
                    content_hash,
                    size_bytes,
                    now,
                    now,
                ),
            )
            return
        if str(row["path_key"]) != path_key:
            raise ExternalCourseKnowledgeConflictError(
                "knowledge document ID is bound to another portable path"
            )
        changed = str(row["content_hash"]) != content_hash
        status_sql = (
            ",extraction_status='pending',extraction_version='',extraction_error=NULL"
            if reset_extraction and changed
            else ""
        )
        self.connection.execute(
            "UPDATE knowledge_documents SET kind=?,mime_type=?,content_hash=?,"
            "size_bytes=?,updated_at=?{} WHERE id=?".format(status_sql),
            (kind, mime_type, content_hash, size_bytes, now, document_id),
        )
