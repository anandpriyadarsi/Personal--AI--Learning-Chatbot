"""Read-only operator verifier for Phase 5.9 final closure."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

from obsidian_integration import get_vault_path
from personal_learning_assistant.ingestion.external_course_package import (
    MIT1806PackageReader,
    discover_mit1806_package,
)
from personal_learning_assistant.repositories.sqlite.external_course_knowledge_repository import (
    SQLiteExternalCourseKnowledgeRepository,
)
from personal_learning_assistant.services.external_course_crosswalk_service import (
    ExternalCourseCrosswalkService,
)
from personal_learning_assistant.services.phase5_closure_service import (
    Phase5ClosureError,
    Phase5ClosureService,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Verify Phase 5 final reconciliation/closure without writes."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--database", default="data/learning_assistant.db")
    parser.add_argument("--authority", default=".phase4_authority.json")
    parser.add_argument("--index-root", default=".phase5_retrieval")
    parser.add_argument("--crosswalk", required=True)
    parser.add_argument("--package-key", default="mit1806-package")
    parser.add_argument("--local-course", default="MA103N")
    package = parser.add_mutually_exclusive_group(required=True)
    package.add_argument("--configured-vault", action="store_true")
    package.add_argument("--package-root")
    return parser


def _uri(path: Path):
    value = str(path.resolve(strict=False)).replace("\\", "/")
    return "file:{}?mode=ro".format(quote(value, safe="/:"))


def _authority(path: Path):
    if not path.is_file() or path.is_symlink():
        raise Phase5ClosureError("Phase 4 authority-control file is missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("storage_backend") != "sqlite":
        raise Phase5ClosureError("SQLite is not the active Phase 4 authority")
    if value.get("legacy_writes_blocked") is not True:
        raise Phase5ClosureError("legacy structured writes are not blocked")
    return {
        "storage_backend": value.get("storage_backend"),
        "legacy_writes_blocked": value.get("legacy_writes_blocked"),
        "cutover_id": value.get("cutover_id", ""),
        "promoted_at": value.get("promoted_at", ""),
    }


def main(argv=None):
    args = _parser().parse_args(argv)
    project_root = Path(args.project_root).resolve(strict=False)
    db_path = (project_root / args.database).resolve(strict=False)
    authority_path = (project_root / args.authority).resolve(strict=False)
    index_root = (project_root / args.index_root).resolve(strict=False)
    crosswalk_path = Path(args.crosswalk).resolve(strict=False)

    rebuild_root = Path(tempfile.mkdtemp(prefix="phase5-closure-rebuild-"))
    try:
        authority = _authority(authority_path)
        if args.configured_vault:
            vault = get_vault_path()
            if not vault:
                raise Phase5ClosureError(
                    "no enabled valid Obsidian vault is configured"
                )
            package_root = discover_mit1806_package(vault)
        else:
            package_root = Path(args.package_root).resolve(strict=False)
        package = MIT1806PackageReader(package_root).load()

        if not db_path.is_file() or db_path.is_symlink():
            raise Phase5ClosureError(
                "production SQLite database is missing/not a regular file"
            )
        connection = sqlite3.connect(
            _uri(db_path),
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            external_repo = SQLiteExternalCourseKnowledgeRepository(connection)
            reviewed = ExternalCourseCrosswalkService(
                external_repo
            ).load_reviewed(
                crosswalk_path,
                package,
                local_course_code=args.local_course,
                require_complete=True,
            )
            report = Phase5ClosureService(
                connection,
                index_root=index_root,
            ).verify(
                package=package,
                reviewed_crosswalk=reviewed,
                package_key=args.package_key,
                local_course_code=args.local_course,
                rebuild_root=rebuild_root,
            )
        finally:
            connection.close()

        output = {
            "authority": authority,
            "core": report["core"],
            "external_course": report["external_course"],
            "retrieval": report["retrieval"],
            "issue_count": report["issue_count"],
            "production_writes_performed": False,
            "source_files_modified": False,
            "current_index_modified": False,
            "rebuild_rehearsal_isolated": True,
            "llm_called": False,
        }
        print("PHASE 5 FINAL RECONCILIATION/CLOSURE: PASS")
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error, Phase5ClosureError) as error:
        print("PHASE 5 FINAL RECONCILIATION/CLOSURE: BLOCKED", file=sys.stderr)
        print("{}: {}".format(type(error).__name__, error), file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(rebuild_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
