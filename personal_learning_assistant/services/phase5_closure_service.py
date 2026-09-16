"""Phase 5.9 final reconciliation and closure verification.

The verifier is intentionally read-only with respect to authoritative SQLite.
A rebuild rehearsal writes only to a caller-supplied temporary derived-index
directory and never acknowledges jobs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from personal_learning_assistant.ingestion.chunking import decode_chunk_type
from personal_learning_assistant.repositories.sqlite.external_course_knowledge_repository import (
    SQLiteExternalCourseKnowledgeRepository,
    resource_external_id,
)
from personal_learning_assistant.repositories.sqlite.retrieval_source_repository import (
    SQLiteRetrievalSourceRepository,
)
from personal_learning_assistant.retrieval.index_builder import RetrievalIndexBuilder
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.external_course_crosswalk_service import (
    ExternalCourseCrosswalkService,
)
from personal_learning_assistant.services.retrieval_service import RetrievalService


class Phase5ClosureError(RuntimeError):
    pass


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _lecture_refs(locator):
    refs = {
        str(item)
        for item in locator.get("lecture_numbers", ())
        if item is not None and str(item)
    }
    one = locator.get("lecture_number")
    if one is not None and str(one):
        refs.add(str(one))
    return refs


class Phase5ClosureService:
    def __init__(self, connection: sqlite3.Connection, *, index_root):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.index_root = Path(index_root)
        self.retrieval_repository = SQLiteRetrievalSourceRepository(connection)
        self.external_repository = SQLiteExternalCourseKnowledgeRepository(connection)
        self.crosswalk_service = ExternalCourseCrosswalkService(
            self.external_repository
        )

    def verify(
        self,
        *,
        package,
        reviewed_crosswalk,
        package_key: str,
        local_course_code: str,
        rebuild_root,
        smoke_query: str = "LU factorization triangular matrices",
        smoke_provider: str = "mit_ocw",
        smoke_lecture: str = "04",
    ):
        issues = []
        report = {}

        self._verify_core(report, issues)
        install = self._verify_external_course(
            package=package,
            reviewed_crosswalk=reviewed_crosswalk,
            package_key=package_key,
            local_course_code=local_course_code,
            issues=issues,
        )
        report["external_course"] = install

        retrieval = self._verify_retrieval(
            rebuild_root=Path(rebuild_root),
            smoke_query=smoke_query,
            smoke_provider=smoke_provider,
            smoke_lecture=smoke_lecture,
            issues=issues,
        )
        report["retrieval"] = retrieval

        report["issue_count"] = len(issues)
        report["issues"] = tuple(issues)
        if issues:
            raise Phase5ClosureError(
                "Phase 5 closure reconciliation failed:\n- {}".format(
                    "\n- ".join(issues)
                )
            )
        return report

    def _verify_core(self, report, issues):
        integrity = str(
            self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        foreign_keys = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if integrity != "ok":
            issues.append("PRAGMA integrity_check returned {!r}".format(integrity))
        if foreign_keys:
            issues.append(
                "PRAGMA foreign_key_check reported {} violation(s)".format(
                    len(foreign_keys)
                )
            )

        versions = tuple(
            int(row[0])
            for row in self.connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        if len(versions) < 2 or versions[:2] != (1, 2):
            issues.append(
                "unexpected migration history {}; Phase 5 requires intact 0001/0002 prefix".format(
                    versions
                )
            )

        duplicate_paths = self.connection.execute(
            "SELECT path_key,COUNT(*) AS n FROM knowledge_documents "
            "WHERE path_key IS NOT NULL AND trim(path_key)<>'' "
            "GROUP BY path_key HAVING COUNT(*)>1"
        ).fetchall()
        if duplicate_paths:
            issues.append(
                "{} duplicate knowledge document path_key group(s) exist".format(
                    len(duplicate_paths)
                )
            )

        duplicate_external = self.connection.execute(
            "SELECT lower(provider),external_id,COUNT(*) AS n FROM resources "
            "WHERE deleted_at IS NULL AND external_id IS NOT NULL "
            "AND trim(external_id)<>'' "
            "GROUP BY lower(provider),external_id HAVING COUNT(*)>1"
        ).fetchall()
        if duplicate_external:
            issues.append(
                "{} duplicate active resource external-identity group(s) exist".format(
                    len(duplicate_external)
                )
            )

        completed_without_chunks = self.connection.execute(
            "SELECT d.id FROM knowledge_documents d "
            "WHERE d.extraction_status='completed' AND d.extraction_version<>'' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM knowledge_chunks c "
            "  WHERE c.document_id=d.id "
            "  AND c.extraction_version=d.extraction_version "
            "  AND c.chunk_text IS NOT NULL"
            ")"
        ).fetchall()
        if completed_without_chunks:
            issues.append(
                "{} completed document(s) have no current retrievable chunks".format(
                    len(completed_without_chunks)
                )
            )

        nonterminal_operations = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM operation_journal "
                "WHERE state NOT IN ('completed','failed')"
            ).fetchone()[0]
        )
        if nonterminal_operations:
            issues.append(
                "{} operation journal row(s) remain non-terminal".format(
                    nonterminal_operations
                )
            )

        counts = {}
        for table in (
            "vaults",
            "note_metadata",
            "note_links",
            "resources",
            "resource_courses",
            "resource_topics",
            "resource_documents",
            "knowledge_documents",
            "knowledge_chunks",
            "index_jobs",
            "operation_journal",
            "outbox_events",
        ):
            counts[table] = int(
                self.connection.execute(
                    'SELECT COUNT(*) FROM "{}"'.format(table)
                ).fetchone()[0]
            )

        report["core"] = {
            "integrity_check": integrity,
            "foreign_key_violation_count": len(foreign_keys),
            "migration_versions": versions,
            "duplicate_document_path_count": len(duplicate_paths),
            "duplicate_resource_external_identity_count": len(duplicate_external),
            "completed_document_without_current_chunk_count": len(
                completed_without_chunks
            ),
            "nonterminal_operation_count": nonterminal_operations,
            "failed_operation_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM operation_journal WHERE state='failed'"
                ).fetchone()[0]
            ),
            "pending_outbox_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM outbox_events "
                    "WHERE processed_at IS NULL AND failed_at IS NULL"
                ).fetchone()[0]
            ),
            "failed_outbox_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM outbox_events "
                    "WHERE failed_at IS NOT NULL"
                ).fetchone()[0]
            ),
            "table_counts": counts,
        }

    def _verify_external_course(
        self,
        *,
        package,
        reviewed_crosswalk,
        package_key,
        local_course_code,
        issues,
    ):
        crosswalk_preview = self.crosswalk_service.preview(
            package,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )
        if not crosswalk_preview.crosswalk_complete:
            issues.append("reviewed MIT/MA103N crosswalk is not complete")
        if crosswalk_preview.pending_review_label_count:
            issues.append(
                "{} crosswalk label(s) remain pending review".format(
                    crosswalk_preview.pending_review_label_count
                )
            )

        (
            local_course_id,
            label_topic_ids,
            lecture_topic_ids,
            course_topic_ids,
        ) = self.crosswalk_service.resolve_all(
            package,
            local_course_code=local_course_code,
            reviewed_crosswalk=reviewed_crosswalk,
        )

        course_external_id = resource_external_id(package.course_id)
        course_resource_id = self.external_repository.find_resource_by_external_identity(
            "mit_ocw", course_external_id
        )
        if not course_resource_id:
            issues.append("MIT external-course resource is missing")

        lecture_resource_ids = {}
        for lecture in package.lectures:
            resource_id = self.external_repository.find_resource_by_external_identity(
                "mit_ocw",
                resource_external_id(package.course_id, lecture.lecture_number),
            )
            if not resource_id:
                issues.append(
                    "MIT lecture resource {} is missing".format(
                        lecture.lecture_number
                    )
                )
            else:
                lecture_resource_ids[lecture.lecture_number] = resource_id

        if course_resource_id:
            course_link = self.connection.execute(
                "SELECT 1 FROM resource_courses WHERE resource_id=? "
                "AND course_id=? AND role='external_course'",
                (course_resource_id, local_course_id),
            ).fetchone()
            if course_link is None:
                issues.append("MIT external-course resource is not linked to MA103N")

            actual_course_topics = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT topic_id FROM resource_topics WHERE resource_id=?",
                    (course_resource_id,),
                )
            }
            if actual_course_topics != set(course_topic_ids):
                issues.append(
                    "MIT course-level reviewed topic links differ from crosswalk"
                )

        for lecture_number, resource_id in lecture_resource_ids.items():
            course_link = self.connection.execute(
                "SELECT 1 FROM resource_courses WHERE resource_id=? "
                "AND course_id=? AND role='supporting'",
                (resource_id, local_course_id),
            ).fetchone()
            if course_link is None:
                issues.append(
                    "MIT lecture {} is not linked to MA103N".format(
                        lecture_number
                    )
                )
            actual_topics = {
                str(row[0])
                for row in self.connection.execute(
                    "SELECT topic_id FROM resource_topics WHERE resource_id=?",
                    (resource_id,),
                )
            }
            expected_topics = set(lecture_topic_ids.get(lecture_number, ()))
            if actual_topics != expected_topics:
                issues.append(
                    "MIT lecture {} topic links differ from reviewed crosswalk".format(
                        lecture_number
                    )
                )

        specs = (
            (
                "external_course_manifest",
                "{}/course_manifest.json".format(package_key),
                package.manifest_sha256,
            ),
            (
                "external_course_inventory",
                "{}/lecture_inventory.json".format(package_key),
                package.inventory_sha256,
            ),
            (
                "external_course_schema",
                "{}/schema.json".format(package_key),
                package.schema_sha256,
            ),
            (
                "external_course_chunks",
                "{}/chunks.jsonl".format(package_key),
                package.chunks_sha256,
            ),
        )
        document_ids = {}
        for kind, path_key, content_hash in specs:
            rows = self.connection.execute(
                "SELECT id,kind,content_hash FROM knowledge_documents "
                "WHERE path_key=?",
                (path_key,),
            ).fetchall()
            if len(rows) != 1:
                issues.append(
                    "package document {} resolves to {} rows".format(
                        path_key, len(rows)
                    )
                )
                continue
            row = rows[0]
            document_ids[kind] = str(row["id"])
            if str(row["kind"]) != kind:
                issues.append("{} has wrong document kind".format(path_key))
            if str(row["content_hash"]) != content_hash:
                issues.append("{} content hash differs from package".format(path_key))

        chunks_document_id = document_ids.get("external_course_chunks")
        chunk_count = 0
        local_topic_ids_seen = set()
        if chunks_document_id:
            doc = self.connection.execute(
                "SELECT extraction_status,extraction_version FROM knowledge_documents "
                "WHERE id=?",
                (chunks_document_id,),
            ).fetchone()
            if doc is None or str(doc["extraction_status"]) != "completed":
                issues.append("MIT chunks document is not completed")
            else:
                extraction_version = str(doc["extraction_version"])
                rows = self.connection.execute(
                    "SELECT id,ordinal,chunk_type,text_hash,chunk_text "
                    "FROM knowledge_chunks WHERE document_id=? "
                    "AND extraction_version=? ORDER BY ordinal,id",
                    (chunks_document_id, extraction_version),
                ).fetchall()
                chunk_count = len(rows)
                if chunk_count != len(package.chunks):
                    issues.append(
                        "MIT current chunk count {} != package {}".format(
                            chunk_count, len(package.chunks)
                        )
                    )
                package_by_id = {
                    chunk.chunk_id: chunk for chunk in package.chunks
                }
                seen_package_ids = set()
                for row in rows:
                    _kind, locator = decode_chunk_type(str(row["chunk_type"]))
                    package_chunk_id = str(
                        locator.get("package_chunk_id") or ""
                    )
                    package_chunk = package_by_id.get(package_chunk_id)
                    if package_chunk is None:
                        issues.append(
                            "current MIT chunk {} lacks valid package_chunk_id".format(
                                row["id"]
                            )
                        )
                        continue
                    if package_chunk_id in seen_package_ids:
                        issues.append(
                            "duplicate current package chunk identity {}".format(
                                package_chunk_id
                            )
                        )
                    seen_package_ids.add(package_chunk_id)

                    if str(row["text_hash"]) != package_chunk.content_hash:
                        issues.append(
                            "{} text hash differs from package".format(
                                package_chunk_id
                            )
                        )
                    if str(row["chunk_text"]) != package_chunk.text:
                        issues.append(
                            "{} text differs from package".format(
                                package_chunk_id
                            )
                        )
                    if locator.get("external_course_id") != package.course_id:
                        issues.append(
                            "{} external course provenance differs".format(
                                package_chunk_id
                            )
                        )
                    if (
                        locator.get("crosswalk_sha256")
                        != reviewed_crosswalk.crosswalk_sha256
                    ):
                        issues.append(
                            "{} crosswalk hash differs from reviewed artifact".format(
                                package_chunk_id
                            )
                        )
                    source = locator.get("source")
                    if (
                        not isinstance(source, dict)
                        or source.get("provider") != "MIT OpenCourseWare"
                    ):
                        issues.append(
                            "{} MIT source provider provenance is missing".format(
                                package_chunk_id
                            )
                        )

                    expected_local = {
                        label_topic_ids[key]
                        for key in (
                            _norm(package_chunk.topic),
                            *(_norm(item) for item in package_chunk.concepts),
                        )
                        if key in label_topic_ids
                    }
                    actual_local = {
                        str(item)
                        for item in locator.get("local_topic_ids", ())
                        if str(item)
                    }
                    local_topic_ids_seen.update(actual_local)
                    if actual_local != expected_local:
                        issues.append(
                            "{} local topic provenance differs from crosswalk".format(
                                package_chunk_id
                            )
                        )

                if seen_package_ids != set(package_by_id):
                    issues.append(
                        "current SQLite package chunk identities do not exactly "
                        "cover the package"
                    )

        return {
            "course_id": package.course_id,
            "package_version": package.version,
            "local_course_code": local_course_code,
            "local_course_id": local_course_id,
            "lecture_count": len(package.lectures),
            "chunk_count": chunk_count,
            "package_document_count": len(document_ids),
            "resource_count": (
                (1 if course_resource_id else 0) + len(lecture_resource_ids)
            ),
            "crosswalk_complete": crosswalk_preview.crosswalk_complete,
            "crosswalk_sha256": reviewed_crosswalk.crosswalk_sha256,
            "reviewed_mapped_label_count": (
                crosswalk_preview.reviewed_mapped_label_count
            ),
            "reviewed_unresolved_label_count": (
                crosswalk_preview.reviewed_unresolved_label_count
            ),
            "pending_review_label_count": (
                crosswalk_preview.pending_review_label_count
            ),
            "mapped_local_topic_id_count": len(local_topic_ids_seen),
        }

    def _verify_retrieval(
        self,
        *,
        rebuild_root,
        smoke_query,
        smoke_provider,
        smoke_lecture,
        issues,
    ):
        builder = RetrievalIndexBuilder(
            self.retrieval_repository, self.index_root
        )
        manifest = builder.read_current_manifest()
        records = self.retrieval_repository.active_records()
        fingerprint = self.retrieval_repository.source_fingerprint()

        if manifest is None:
            issues.append("current Phase 5.8 retrieval manifest is missing")
            return {
                "active_document_count": len(
                    {record["document_id"] for record in records}
                ),
                "active_chunk_count": len(records),
                "source_fingerprint": fingerprint,
                "current_generation_id": "",
                "rebuild_generation_id": "",
                "current_index_valid": False,
                "rebuild_matches_current": False,
                "smoke_hit_count": 0,
            }

        current_valid = builder.verify_manifest_files(manifest)
        if not current_valid:
            issues.append("current Phase 5.8 retrieval index files fail manifest hashes")
        if str(manifest.get("source_fingerprint")) != fingerprint:
            issues.append(
                "current retrieval index fingerprint differs from authoritative chunks"
            )
        if int(manifest.get("chunk_count", -1)) != len(records):
            issues.append(
                "current retrieval manifest chunk count differs from authoritative chunks"
            )
        if bool(manifest.get("semantic_enabled")):
            issues.append(
                "Phase 5 closure expects the verified current production generation "
                "to be the lexical baseline; semantic promotion belongs after closure"
            )

        current_generation = str(manifest.get("generation_id") or "")
        active_documents = {
            record["document_id"]: record["content_hash"] for record in records
        }
        current_jobs = self.connection.execute(
            "SELECT document_id,content_hash,status FROM index_jobs "
            "WHERE index_kind='lexical_retrieval' AND index_version=?",
            (current_generation,),
        ).fetchall()
        current_job_map = {
            str(row["document_id"]): (
                str(row["content_hash"]),
                str(row["status"]),
            )
            for row in current_jobs
        }
        for document_id, content_hash in active_documents.items():
            value = current_job_map.get(document_id)
            if value != (content_hash, "completed"):
                issues.append(
                    "active document {} lacks a completed current lexical job".format(
                        document_id
                    )
                )

        pending_handoffs = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM index_jobs "
                "WHERE index_kind='retrieval_handoff' AND status='pending'"
            ).fetchone()[0]
        )
        if pending_handoffs:
            issues.append(
                "{} retrieval handoff job(s) remain pending".format(
                    pending_handoffs
                )
            )

        smoke_hit_count = 0
        context_source_count = 0
        current_hits = ()
        if current_valid:
            store = RetrievalIndexStore(self.index_root)
            try:
                service = RetrievalService(store)
                hits = service.search(
                    smoke_query,
                    providers=(smoke_provider,),
                    lecture_numbers=(smoke_lecture,),
                    top_k=5,
                )
                current_hits = hits
                smoke_hit_count = len(hits)
                if not hits:
                    issues.append("current retrieval smoke query returned no hits")
                else:
                    locator = dict(hits[0].locator or {})
                    if str(smoke_lecture) not in _lecture_refs(locator):
                        issues.append(
                            "current retrieval smoke hit lost lecture provenance"
                        )
                    source = locator.get("source")
                    if (
                        not isinstance(source, dict)
                        or source.get("provider") != "MIT OpenCourseWare"
                    ):
                        issues.append(
                            "current retrieval smoke hit lost MIT provider provenance"
                        )
                context = service.build_context(
                    smoke_query,
                    providers=(smoke_provider,),
                    lecture_numbers=(smoke_lecture,),
                    top_k=5,
                    max_chars=8000,
                )
                context_source_count = context.source_count
                if context.source_count == 0:
                    issues.append("RAG context smoke assembly returned no sources")
                if "locator=" in context.context_text:
                    issues.append(
                        "RAG context reverted to verbose raw locator JSON"
                    )
                if "chunk_id=" not in context.context_text:
                    issues.append(
                        "RAG context is missing explicit chunk provenance"
                    )
            finally:
                store.close()

        rebuild_root = Path(rebuild_root)
        rebuild_builder = RetrievalIndexBuilder(
            self.retrieval_repository, rebuild_root
        )
        rebuilt = rebuild_builder.build(
            embedding_provider=None,
            acknowledge=False,
        )
        rebuild_manifest = rebuild_builder.read_current_manifest()
        rebuild_valid = bool(
            rebuild_manifest
            and rebuild_builder.verify_manifest_files(rebuild_manifest)
        )
        if not rebuild_valid:
            issues.append("fresh lexical rebuild rehearsal failed manifest verification")
        rebuild_matches = rebuilt.generation_id == current_generation
        if not rebuild_matches:
            issues.append(
                "fresh lexical rebuild generation differs from current production index"
            )

        if rebuild_valid:
            rebuild_store = RetrievalIndexStore(rebuild_root)
            try:
                rebuilt_hits = RetrievalService(rebuild_store).search(
                    smoke_query,
                    providers=(smoke_provider,),
                    lecture_numbers=(smoke_lecture,),
                    top_k=5,
                )
                if not rebuilt_hits:
                    issues.append(
                        "fresh lexical rebuild cannot reproduce retrieval smoke hit"
                    )
                elif current_hits and rebuilt_hits[0].chunk_id != current_hits[0].chunk_id:
                    issues.append(
                        "fresh lexical rebuild top smoke hit differs from current index"
                    )
            finally:
                rebuild_store.close()

        counts = self.retrieval_repository.handoff_counts()
        return {
            "active_document_count": len(active_documents),
            "active_chunk_count": len(records),
            "source_fingerprint": fingerprint,
            "current_generation_id": current_generation,
            "current_index_valid": current_valid,
            "current_lexical_backend": str(
                manifest.get("lexical_backend") or ""
            ),
            "current_semantic_enabled": bool(
                manifest.get("semantic_enabled")
            ),
            "pending_handoff_count": pending_handoffs,
            "handoff_counts": counts,
            "completed_current_lexical_job_count": sum(
                1
                for document_id, (content_hash, status) in current_job_map.items()
                if (
                    document_id in active_documents
                    and active_documents[document_id] == content_hash
                    and status == "completed"
                )
            ),
            "smoke_hit_count": smoke_hit_count,
            "context_source_count": context_source_count,
            "rebuild_generation_id": rebuilt.generation_id,
            "rebuild_manifest_valid": rebuild_valid,
            "rebuild_matches_current": rebuild_matches,
        }
