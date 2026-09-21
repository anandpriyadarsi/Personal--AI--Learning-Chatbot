"""Read-only Moodle discovery plus explicit local sync into ANVAYA knowledge files.

Remote Moodle is never modified. Sync downloads only supported learning files,
records provenance in SQLite, registers the local files in the existing
knowledge registry, and runs the existing local extraction pipeline. Retrieval
indexes remain disposable and must be rebuilt after new chunks are ingested.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from personal_learning_assistant.integrations.moodle_client import (
    MoodleClient,
    MoodleClientError,
)
from personal_learning_assistant.repositories.sqlite.moodle_sync_repository import (
    MoodleSyncRepositoryError,
    SQLiteMoodleSyncRepository,
)


_ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".txt", ".md"}
_NAMESPACE = uuid.UUID("fc7aa3b2-2efa-4ef4-95ed-4e0606b330d2")


class MoodleSyncError(RuntimeError):
    """Safe Moodle sync failure."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_component(value, fallback):
    text = re.sub(r"[^A-Za-z0-9._ -]+", "-", str(value or "").strip())
    text = " ".join(text.split()).strip(" .-")
    return (text[:100] or fallback)


def _file_id(course_id, module_id, file_url):
    return str(
        uuid.uuid5(
            _NAMESPACE,
            "moodle-file|{}|{}|{}".format(course_id, module_id, file_url),
        )
    )


def _open_existing_database(path):
    database = Path(path)
    if not database.is_file() or database.is_symlink():
        raise MoodleSyncError("Academic database is unavailable.")
    uri = "file:{}?mode=rw".format(
        quote(str(database.resolve(strict=False)).replace("\\", "/"), safe="/:")
    )
    try:
        c = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=5000")
        return c
    except sqlite3.Error as error:
        raise MoodleSyncError("Academic database is unavailable.") from error


class MoodleSyncService:
    def __init__(
        self,
        *,
        client,
        repository,
        database_path="data/learning_assistant.db",
        root_path="knowledge/moodle",
        now=_now,
    ):
        self.client = client
        self.repository = repository
        self.database_path = Path(database_path)
        self.root_path = Path(root_path)
        self._now = now

    @property
    def configured(self):
        return self.client is not None

    def status(self):
        recent = ()
        migration_ready = True
        try:
            recent = self.repository.list_files(limit=40)
        except MoodleSyncRepositoryError:
            migration_ready = False
        return {
            "configured": self.configured,
            "migration_ready": migration_ready,
            "root_path": self.root_path.as_posix(),
            "recent": recent,
        }

    def _course_mapping(self, course):
        shortname = str(course.get("shortname") or "")
        fullname = str(course.get("fullname") or course.get("displayname") or "")
        haystack = "{} {}".format(shortname, fullname).casefold()
        try:
            candidates = [
                row
                for row in self.repository.courses()
                if str(row.get("code") or "").casefold() in haystack
            ]
        except MoodleSyncRepositoryError as error:
            raise MoodleSyncError(str(error)) from error
        return candidates[0]["id"] if len(candidates) == 1 else None

    @staticmethod
    def _iter_files(course, sections):
        for section in sections:
            for module in tuple(section.get("modules") or ()):
                module_id = str(module.get("id") or "")
                module_name = str(module.get("name") or module.get("modname") or "")
                for item in tuple(module.get("contents") or ()):
                    if str(item.get("type") or "file").casefold() != "file":
                        continue
                    filename = str(item.get("filename") or "").strip()
                    file_url = str(item.get("fileurl") or "").strip()
                    if not filename or not file_url:
                        continue
                    if Path(filename).suffix.casefold() not in _ALLOWED_EXTENSIONS:
                        continue
                    yield {
                        "moodle_course_id": str(course.get("id") or ""),
                        "course_shortname": str(course.get("shortname") or ""),
                        "course_name": str(
                            course.get("fullname") or course.get("displayname") or ""
                        ),
                        "module_id": module_id,
                        "module_name": module_name,
                        "file_name": filename,
                        "file_url": file_url,
                        "mime_type": str(item.get("mimetype") or ""),
                        "external_content_hash": str(
                            item.get("contenthash") or item.get("content_hash") or ""
                        ),
                        "external_modified_at": str(
                            item.get("timemodified") or item.get("timecreated") or ""
                        ),
                    }

    def _remote_files(self):
        if self.client is None:
            raise MoodleSyncError(
                "Moodle is not configured. Set ANVAYA_MOODLE_BASE_URL and ANVAYA_MOODLE_TOKEN."
            )
        try:
            site = self.client.site_info()
            courses = self.client.enrolled_courses(site["userid"])
            files = []
            for course in courses:
                sections = self.client.course_contents(course.get("id"))
                anvaya_course_id = self._course_mapping(course)
                for item in self._iter_files(course, sections):
                    item["anvaya_course_id"] = anvaya_course_id
                    files.append(item)
            return tuple(files)
        except (MoodleClientError, MoodleSyncRepositoryError, ValueError) as error:
            raise MoodleSyncError(str(error)) from error

    def preview(self):
        remote = self._remote_files()
        rows = []
        for item in remote:
            try:
                existing = self.repository.find_file(
                    item["moodle_course_id"], item["module_id"], item["file_url"]
                )
            except MoodleSyncRepositoryError as error:
                raise MoodleSyncError(str(error)) from error
            state = "new"
            if existing is not None:
                hash_changed = (
                    bool(item["external_content_hash"])
                    and item["external_content_hash"]
                    != str(existing.get("external_content_hash") or "")
                )
                time_changed = (
                    bool(item["external_modified_at"])
                    and item["external_modified_at"]
                    != str(existing.get("external_modified_at") or "")
                )
                local_ok = (
                    str(existing.get("status") or "") == "downloaded"
                    and bool(existing.get("local_path"))
                    and Path(str(existing["local_path"])).is_file()
                )
                state = "changed" if (hash_changed or time_changed or not local_ok) else "current"
            rows.append({**item, "state": state})
        return {
            "configured": True,
            "files": tuple(rows),
            "summary": {
                "new": sum(1 for row in rows if row["state"] == "new"),
                "changed": sum(1 for row in rows if row["state"] == "changed"),
                "current": sum(1 for row in rows if row["state"] == "current"),
                "total": len(rows),
            },
        }

    def _target_path(self, item):
        course = _safe_component(
            item.get("course_shortname") or item.get("course_name"),
            "course-{}".format(item["moodle_course_id"]),
        )
        module = _safe_component(item.get("module_name"), "module-{}".format(item["module_id"]))
        filename = _safe_component(item["file_name"], "resource")
        target = self.root_path / course / module / filename
        root = self.root_path.resolve(strict=False)
        resolved = target.resolve(strict=False)
        if resolved == root or root not in resolved.parents:
            raise MoodleSyncError("Moodle target path escaped the configured knowledge root.")
        return target

    def _write_download(self, item, payload):
        target = self._target_path(item)
        if target.exists() and target.is_symlink():
            raise MoodleSyncError("Moodle target is an unsafe symlink.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise MoodleSyncError("Moodle target directory is an unsafe symlink.")
        temporary = target.with_name("." + target.name + ".anvaya.tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(str(temporary), str(target))
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    def _register_and_ingest(self, synced_items):
        """Reuse Phase 5 registry/extraction and link downloads into Resources 2."""
        from personal_learning_assistant.ingestion.source_resolver import (
            SourceRootResolver,
        )
        from personal_learning_assistant.repositories.filesystem.source_scanner import (
            FileSystemSourceScanner,
        )
        from personal_learning_assistant.repositories.sqlite.ingestion_repository import (
            SQLiteIngestionRepository,
        )
        from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
            SQLiteKnowledgeRegistryRepository,
        )
        from personal_learning_assistant.services.knowledge_registry_service import (
            KnowledgeRegistryService,
        )
        from personal_learning_assistant.services.source_scanner_service import (
            DocumentSourceScannerService,
        )
        from personal_learning_assistant.services.unified_ingestion_service import (
            UnifiedIngestionService,
        )
        from personal_learning_assistant.domain.resources2_models import (
            CreateResource2Command,
            ResourceCourseLink,
            ResourceDocumentLink,
            UpdateResource2Command,
        )
        from personal_learning_assistant.repositories.sqlite.resources2_repository import (
            SQLiteResources2Repository,
        )
        from personal_learning_assistant.services.resources2_service import (
            Resources2Service,
        )

        if not self.root_path.is_dir():
            return {"registered": 0, "ingested": 0, "failed": 0}
        scan = FileSystemSourceScanner("moodle", self.root_path).scan()
        if scan.issues:
            raise MoodleSyncError(
                "Downloaded Moodle files contain unresolved local scan issues."
            )

        connection = _open_existing_database(self.database_path)
        try:
            registry_repository = SQLiteKnowledgeRegistryRepository(connection)
            registry = KnowledgeRegistryService(registry_repository)
            registration = DocumentSourceScannerService(
                registry_repository, registry
            ).apply(scan)
            ingestion = UnifiedIngestionService(
                SQLiteIngestionRepository(connection),
                SourceRootResolver({"moodle": self.root_path}),
            )
            results = tuple(
                ingestion.ingest_document(item.document_id)
                for item in registration.items
            )

            path_to_document = {
                str(item.path_key): str(item.document_id)
                for item in registration.items
            }
            resources = Resources2Service(
                SQLiteResources2Repository(connection)
            )
            linked_resources = 0
            for remote in tuple(synced_items or ()):
                target = self._target_path(remote)
                try:
                    relative = target.resolve(strict=False).relative_to(
                        self.root_path.resolve(strict=False)
                    ).as_posix()
                except ValueError:
                    continue
                document_id = path_to_document.get("moodle/" + relative)
                if not document_id:
                    continue
                external_id = "{}:{}:{}".format(
                    remote["moodle_course_id"],
                    remote.get("module_id", ""),
                    hashlib.sha256(
                        str(remote["file_url"]).encode("utf-8")
                    ).hexdigest()[:20],
                )
                course_links = (
                    ()
                    if not remote.get("anvaya_course_id")
                    else (
                        ResourceCourseLink(
                            str(remote["anvaya_course_id"]),
                            "primary",
                        ),
                    )
                )
                document_links = (
                    ResourceDocumentLink(document_id, "source"),
                )
                candidates = resources.get_duplicate_candidates(
                    title=remote["file_name"],
                    canonical_uri=remote["file_url"],
                    provider="moodle",
                    external_id=external_id,
                    document_ids=(document_id,),
                )
                exact = tuple(
                    candidate
                    for candidate in candidates
                    if "provider_external_id" in candidate.reasons
                    or "document_content_hash" in candidate.reasons
                )
                if exact:
                    resource_id = exact[0].resource_id
                    resources.update_resource(
                        UpdateResource2Command(
                            resource_id=resource_id,
                            title=remote["file_name"],
                            canonical_uri=remote["file_url"],
                            provider="moodle",
                            external_id=external_id,
                            quality_note=(
                                "Synced read-only from Moodle: "
                                + str(remote.get("module_name") or "course material")
                            ),
                        )
                    )
                    resources.replace_relationships(
                        resource_id,
                        CreateResource2Command(
                            title=remote["file_name"],
                            resource_type="moodle_file",
                            canonical_uri=remote["file_url"],
                            provider="moodle",
                            external_id=external_id,
                            course_links=course_links,
                            document_links=document_links,
                            allow_duplicate=True,
                        ),
                    )
                else:
                    details = resources.create_resource(
                        CreateResource2Command(
                            title=remote["file_name"],
                            resource_type="moodle_file",
                            canonical_uri=remote["file_url"],
                            provider="moodle",
                            external_id=external_id,
                            status="not_started",
                            quality_note=(
                                "Synced read-only from Moodle: "
                                + str(remote.get("module_name") or "course material")
                            ),
                            course_links=course_links,
                            document_links=document_links,
                            allow_duplicate=False,
                        )
                    )
                    resource_id = details.resource.id
                linked_resources += 1
        finally:
            connection.close()
        return {
            "registered": len(registration.items),
            "ingested": sum(
                1 for result in results if result.action in {"completed", "matched"}
            ),
            "failed": sum(1 for result in results if result.action == "failed"),
            "resources_linked": linked_resources,
        }

    def sync(self):
        preview = self.preview()
        targets = tuple(
            item for item in preview["files"] if item["state"] in {"new", "changed"}
        )
        now = self._now()
        downloaded = 0
        failures = []

        # Sync records every remote file as seen, while preserving existing
        # downloaded status on conflict. Preview itself remains side-effect free.
        for item in preview["files"]:
            target = self._target_path(item)
            row = {
                "id": _file_id(
                    item["moodle_course_id"], item["module_id"], item["file_url"]
                ),
                **item,
                "local_path": target.as_posix(),
                "first_seen_at": now,
                "last_seen_at": now,
            }
            try:
                self.repository.upsert_seen(row)
            except MoodleSyncRepositoryError as error:
                raise MoodleSyncError(str(error)) from error

        for item in targets:
            target = self._target_path(item)
            try:
                payload = self.client.download_file(item["file_url"])
                self._write_download(item, payload)
                self.repository.mark_downloaded(
                    item["moodle_course_id"],
                    item["module_id"],
                    item["file_url"],
                    local_path=target.as_posix(),
                    downloaded_at=now,
                )
                downloaded += 1
            except (MoodleClientError, MoodleSyncRepositoryError, MoodleSyncError, OSError) as error:
                failures.append(
                    {
                        "file_name": item["file_name"],
                        "message": str(error),
                    }
                )
                try:
                    self.repository.mark_failed(
                        item["moodle_course_id"],
                        item["module_id"],
                        item["file_url"],
                        error_text=str(error),
                    )
                except Exception:
                    pass

        ingestion = {
            "registered": 0,
            "ingested": 0,
            "failed": 0,
            "resources_linked": 0,
        }
        if downloaded:
            ingestion = self._register_and_ingest(targets)
        return {
            "downloaded": downloaded,
            "failures": tuple(failures),
            "ingestion": ingestion,
            "index_rebuild_required": bool(downloaded),
            "preview": preview,
        }


def build_moodle_sync_service(
    *,
    database_path="data/learning_assistant.db",
    root_path="knowledge/moodle",
):
    base_url = os.environ.get("ANVAYA_MOODLE_BASE_URL", "").strip()
    token = os.environ.get("ANVAYA_MOODLE_TOKEN", "").strip()
    client = None
    if base_url and token:
        client = MoodleClient(base_url, token)
    return MoodleSyncService(
        client=client,
        repository=SQLiteMoodleSyncRepository(database_path),
        database_path=database_path,
        root_path=root_path,
    )
