"""Generate/validate a reviewed MIT 18.06 ↔ MA103N crosswalk artifact."""

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
    ExternalCourseCrosswalkService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Preview/export/validate MIT 18.06 ↔ local topic crosswalk."
    )
    package = parser.add_mutually_exclusive_group(required=True)
    package.add_argument("--package-root")
    package.add_argument("--configured-vault", action="store_true")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--local-course", default="MA103N")
    parser.add_argument("--crosswalk")
    parser.add_argument("--export-template")
    return parser


def _uri(path: Path):
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode=ro".format(quote(value, safe="/:"))


def _package(args):
    if args.configured_vault:
        vault = get_vault_path()
        if not vault:
            raise ExternalCoursePackageError(
                "no enabled valid Obsidian vault is configured"
            )
        root = discover_mit1806_package(vault)
    else:
        root = Path(args.package_root)
    return MIT1806PackageReader(root).load()


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = _package(args)
        db = Path(args.database)
        if not db.is_file() or db.is_symlink():
            raise RuntimeError("SQLite database is missing or not a regular file")
        connection = sqlite3.connect(
            _uri(db), uri=True, isolation_level=None, timeout=5.0
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            repo = SQLiteExternalCourseKnowledgeRepository(connection)
            service = ExternalCourseCrosswalkService(repo)
            reviewed = None
            if args.crosswalk:
                reviewed = service.load_reviewed(
                    args.crosswalk,
                    package,
                    local_course_code=args.local_course,
                    require_complete=False,
                )
            before = connection.total_changes
            preview = service.preview(
                package,
                local_course_code=args.local_course,
                reviewed_crosswalk=reviewed,
            )
            template = None
            if args.export_template:
                template = service.build_template(
                    package, local_course_code=args.local_course
                )
            if connection.total_changes != before:
                raise RuntimeError("crosswalk preview unexpectedly modified SQLite")
        finally:
            connection.close()

        if args.export_template:
            output = Path(args.export_template)
            output.parent.mkdir(parents=True, exist_ok=True)
            if output.exists():
                raise ExternalCourseCrosswalkError(
                    "refusing to overwrite existing crosswalk template"
                )
            output.write_text(
                json.dumps(template, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        result = {
            "course_id": preview.external_course_id,
            "package_version": preview.package_version,
            "local_course_code": preview.local_course_code,
            "local_course_id": preview.local_course_id,
            "unique_external_label_count": preview.unique_external_label_count,
            "exact_mapped_label_count": preview.exact_mapped_label_count,
            "reviewed_mapped_label_count": preview.reviewed_mapped_label_count,
            "reviewed_unresolved_label_count": preview.reviewed_unresolved_label_count,
            "pending_review_label_count": preview.pending_review_label_count,
            "ambiguous_exact_label_count": preview.ambiguous_exact_label_count,
            "crosswalk_complete": preview.crosswalk_complete,
            "crosswalk_sha256": preview.crosswalk_sha256,
            "sqlite_writes_performed": False,
            "suggestions_auto_applied": False,
            "source_files_modified": False,
            "template_exported": bool(args.export_template),
        }
        print("PHASE 5.7 CROSSWALK RECONCILIATION: PASS")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        sqlite3.Error,
        ExternalCoursePackageError,
        ExternalCourseKnowledgeRepositoryError,
        ExternalCourseCrosswalkError,
    ) as error:
        print("PHASE 5.7 CROSSWALK RECONCILIATION: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
