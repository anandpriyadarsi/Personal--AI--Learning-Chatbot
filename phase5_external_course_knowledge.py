"""Operator CLI for Phase 5.7 MIT 18.06 external-course knowledge."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

from obsidian_integration import get_vault_path
from personal_learning_assistant.ingestion.external_course_package import (
    ExternalCoursePackageError,
    MIT1806PackageReader,
    discover_mit1806_package,
)
from personal_learning_assistant.repositories.sqlite.external_course_knowledge_repository import (
    ExternalCourseKnowledgeRepositoryError,
    SQLiteExternalCourseKnowledgeRepository,
)
from personal_learning_assistant.services.external_course_crosswalk_service import (
    ExternalCourseCrosswalkError,
)
from personal_learning_assistant.services.external_course_knowledge_service import (
    ExternalCourseKnowledgeService,
)


CONFIRMATION_PHRASE = "REGISTER_MIT1806_EXTERNAL_COURSE"


def _parser():
    parser = argparse.ArgumentParser(
        description="Preview/register MIT 18.06 external-course package."
    )
    package = parser.add_mutually_exclusive_group(required=True)
    package.add_argument("--package-root")
    package.add_argument("--configured-vault", action="store_true")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--package-key", default="mit1806-package")
    parser.add_argument("--local-course", default="MA103N")
    parser.add_argument("--crosswalk")
    parser.add_argument("--expect-lectures", type=int)
    parser.add_argument("--expect-chunks", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    return parser


def _uri(path: Path, mode: str):
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode={}".format(quote(value, safe="/:"), mode)


def _open(path: Path, writable: bool):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("SQLite database is missing or not a regular file")
    connection = sqlite3.connect(
        _uri(path, "rw" if writable else "ro"),
        uri=True,
        isolation_level=None,
        timeout=5.0,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.apply and args.confirm != CONFIRMATION_PHRASE:
        print("PHASE 5.7 EXTERNAL COURSE KNOWLEDGE: BLOCKED", file=sys.stderr)
        print(
            "--apply requires --confirm {}".format(CONFIRMATION_PHRASE),
            file=sys.stderr,
        )
        return 2
    if args.apply and not args.crosswalk:
        print("PHASE 5.7 EXTERNAL COURSE KNOWLEDGE: BLOCKED", file=sys.stderr)
        print(
            "--apply requires a complete reviewed --crosswalk artifact",
            file=sys.stderr,
        )
        return 2
    if not args.apply and args.confirm:
        print("--confirm is only valid with --apply", file=sys.stderr)
        return 2

    try:
        if args.configured_vault:
            vault = get_vault_path()
            if not vault:
                raise ExternalCoursePackageError(
                    "no enabled valid Obsidian vault is configured"
                )
            package_root = discover_mit1806_package(vault)
        else:
            package_root = Path(args.package_root)

        package = MIT1806PackageReader(package_root).load()
        if args.expect_lectures is not None and len(package.lectures) != args.expect_lectures:
            raise ExternalCoursePackageError(
                "expected {} lectures but package has {}".format(
                    args.expect_lectures, len(package.lectures)
                )
            )
        if args.expect_chunks is not None and len(package.chunks) != args.expect_chunks:
            raise ExternalCoursePackageError(
                "expected {} chunks but package has {}".format(
                    args.expect_chunks, len(package.chunks)
                )
            )

        connection = _open(Path(args.database), args.apply)
        try:
            repository = SQLiteExternalCourseKnowledgeRepository(connection)
            service = ExternalCourseKnowledgeService(repository)
            reviewed = None
            if args.crosswalk:
                reviewed = service.crosswalk.load_reviewed(
                    args.crosswalk,
                    package,
                    local_course_code=args.local_course,
                    require_complete=args.apply,
                )

            if args.apply:
                result = service.apply(
                    package,
                    package_key=args.package_key,
                    local_course_code=args.local_course,
                    reviewed_crosswalk=reviewed,
                    require_complete_crosswalk=True,
                )
                output = {
                    "mode": "apply",
                    "course_id": package.course_id,
                    "package_version": package.version,
                    "lecture_count": len(package.lectures),
                    "chunk_count": result.chunk_count,
                    "course_resource_id": result.course_resource_id,
                    "lecture_resource_count": result.lecture_resource_count,
                    "knowledge_document_count": result.knowledge_document_count,
                    "mapped_topic_link_count": result.mapped_topic_link_count,
                    "unresolved_topic_label_count": result.unresolved_topic_label_count,
                    "extraction_version": result.extraction_version,
                    "handoff_job_id": result.handoff_job_id,
                    "crosswalk_sha256": reviewed.crosswalk_sha256,
                    "relabeled_as_local_course": False,
                    "semantic_rag_executed": False,
                    "source_files_modified": False,
                }
            else:
                before = connection.total_changes
                result = service.preview(
                    package,
                    package_key=args.package_key,
                    local_course_code=args.local_course,
                    reviewed_crosswalk=reviewed,
                )
                crosswalk_preview = service.crosswalk.preview(
                    package,
                    local_course_code=args.local_course,
                    reviewed_crosswalk=reviewed,
                )
                after = connection.total_changes
                if before != after:
                    raise RuntimeError("preview unexpectedly modified SQLite")
                output = {
                    "mode": "preview",
                    "course_id": result.course_id,
                    "package_version": result.package_version,
                    "lecture_count": result.lecture_count,
                    "chunk_count": result.chunk_count,
                    "lecture_chunk_count": result.lecture_chunk_count,
                    "concept_chunk_count": result.concept_chunk_count,
                    "local_course_code": result.local_course_code,
                    "local_course_id": result.local_course_id,
                    "unique_topic_label_count": result.unique_topic_label_count,
                    "mapped_topic_label_count": result.mapped_topic_label_count,
                    "unresolved_topic_label_count": result.unresolved_topic_label_count,
                    "ambiguous_topic_label_count": result.ambiguous_topic_label_count,
                    "exact_mapped_topic_label_count": crosswalk_preview.exact_mapped_label_count,
                    "reviewed_mapped_topic_label_count": crosswalk_preview.reviewed_mapped_label_count,
                    "reviewed_unresolved_topic_label_count": crosswalk_preview.reviewed_unresolved_label_count,
                    "pending_review_topic_label_count": crosswalk_preview.pending_review_label_count,
                    "crosswalk_complete": crosswalk_preview.crosswalk_complete,
                    "crosswalk_sha256": crosswalk_preview.crosswalk_sha256,
                    "planned_resource_count": result.planned_resource_count,
                    "matched_resource_count": result.matched_resource_count,
                    "planned_document_count": result.planned_document_count,
                    "matched_document_count": result.matched_document_count,
                    "extraction_current": result.extraction_current,
                    "source_manifest_hash": result.source_manifest_hash,
                    "preview_writes_performed": False,
                    "relabeled_as_local_course": False,
                    "semantic_rag_executed": False,
                    "source_files_modified": False,
                }
        finally:
            connection.close()
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        ExternalCoursePackageError,
        ExternalCourseKnowledgeRepositoryError,
        ExternalCourseCrosswalkError,
    ) as error:
        print("PHASE 5.7 EXTERNAL COURSE KNOWLEDGE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1

    print("PHASE 5.7 EXTERNAL COURSE KNOWLEDGE: PASS")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
