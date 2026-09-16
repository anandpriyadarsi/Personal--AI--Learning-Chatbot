"""Phase 5.2 document-registry/source-scan orchestration."""

from __future__ import annotations

from collections import defaultdict

from personal_learning_assistant.domain.source_scanner_models import (
    SourceRegistrationItem,
    SourceRegistrationPlan,
    SourceRegistrationResult,
    SourceScanResult,
)
from personal_learning_assistant.repositories.sqlite.knowledge_registry_repository import (
    KnowledgeRegistryConflictError,
    SQLiteKnowledgeRegistryRepository,
)
from personal_learning_assistant.services.knowledge_registry_service import (
    KnowledgeRegistryService,
)


class SourceScanBlockedError(RuntimeError):
    """Raised when unresolved scanner issues make registration unsafe."""


class DocumentSourceScannerService:
    """Compare/apply source fingerprints without mutating source files."""

    def __init__(
        self,
        registry_repository: SQLiteKnowledgeRegistryRepository,
        registry_service: KnowledgeRegistryService,
    ):
        self.repository = registry_repository
        self.registry = registry_service

    @staticmethod
    def _root_prefix(scan: SourceScanResult) -> str:
        return scan.root.key + "/"

    def _registry_by_path(self, scan: SourceScanResult):
        prefix = self._root_prefix(scan)
        grouped = defaultdict(list)
        for document in self.repository.list_documents():
            if (
                document.path_key
                and document.path_key.startswith(prefix)
            ):
                grouped[document.path_key].append(document)

        conflicts = {
            key: rows
            for key, rows in grouped.items()
            if len(rows) > 1
        }
        if conflicts:
            raise KnowledgeRegistryConflictError(
                "one or more source path keys map to multiple registry rows"
            )

        return {
            key: rows[0]
            for key, rows in grouped.items()
        }

    def _missing_registry_ids(
        self,
        scan: SourceScanResult,
    ):
        registry = self._registry_by_path(scan)
        present = {
            source.path_key
            for source in scan.sources
        }
        return tuple(
            sorted(
                document.id
                for key, document in registry.items()
                if key not in present
            )
        )

    @staticmethod
    def _duplicate_groups(documents):
        by_hash = defaultdict(list)
        for document in documents:
            by_hash[document.content_hash].append(document.id)

        groups = {
            tuple(sorted(ids))
            for ids in by_hash.values()
            if len(set(ids)) > 1
        }
        return tuple(sorted(groups))

    def preview(
        self,
        scan: SourceScanResult,
    ) -> SourceRegistrationPlan:
        registry_by_path = self._registry_by_path(scan)

        create_count = 0
        match_count = 0
        update_count = 0

        for source in scan.sources:
            existing = registry_by_path.get(
                source.path_key
            )
            if existing is None:
                create_count += 1
            elif (
                existing.content_hash
                == source.content_hash
            ):
                match_count += 1
            else:
                update_count += 1

        # Include registered rows and prospective scan identities so
        # same-content candidates are visible before any database write.
        hash_ids = defaultdict(set)

        for document in self.repository.list_documents():
            hash_ids[document.content_hash].add(
                document.id
            )

        for source in scan.sources:
            existing = registry_by_path.get(
                source.path_key
            )
            identity = (
                existing.id
                if existing is not None
                else "scan:" + source.path_key
            )
            hash_ids[source.content_hash].add(
                identity
            )

        duplicate_group_count = sum(
            len(ids) > 1
            for ids in hash_ids.values()
        )

        return SourceRegistrationPlan(
            root_key=scan.root.key,
            scan_manifest_hash=scan.manifest_hash,
            scanned_count=scan.scanned_count,
            create_count=create_count,
            match_count=match_count,
            update_count=update_count,
            duplicate_group_count=(
                duplicate_group_count
            ),
            missing_registry_ids=(
                self._missing_registry_ids(scan)
            ),
            issue_count=len(scan.issues),
            ignored_unsupported=(
                scan.ignored_unsupported
            ),
            ignored_symlinks=scan.ignored_symlinks,
        )

    def apply(
        self,
        scan: SourceScanResult,
        *,
        require_clean_scan: bool = True,
    ) -> SourceRegistrationResult:
        if require_clean_scan and scan.issues:
            raise SourceScanBlockedError(
                "source scan contains {} unresolved issue(s); "
                "registry was not changed".format(
                    len(scan.issues)
                )
            )

        items = []
        registry_before = self._registry_by_path(scan)

        for source in scan.sources:
            existing = registry_before.get(
                source.path_key
            )

            exact_match = (
                existing is not None
                and existing.kind == source.kind
                and existing.mime_type == source.mime_type
                and existing.content_hash == source.content_hash
                and existing.size_bytes == source.size_bytes
                and existing.source_timestamp
                == source.source_timestamp
            )

            if exact_match:
                items.append(
                    SourceRegistrationItem(
                        document_id=existing.id,
                        path_key=source.path_key,
                        action="matched",
                        content_hash=(
                            source.content_hash
                        ),
                        duplicate_candidate_ids=(),
                    )
                )
                continue

            result = self.registry.register_document(
                kind=source.kind,
                path_key=source.path_key,
                content_hash=source.content_hash,
                mime_type=source.mime_type,
                size_bytes=source.size_bytes,
                source_timestamp=(
                    source.source_timestamp
                ),
            )
            items.append(
                SourceRegistrationItem(
                    document_id=result.document.id,
                    path_key=source.path_key,
                    action=result.action,
                    content_hash=source.content_hash,
                    duplicate_candidate_ids=(),
                )
            )

        all_documents = self.repository.list_documents()
        scanned_ids = {
            item.document_id
            for item in items
        }
        duplicate_groups = tuple(
            group
            for group in self._duplicate_groups(
                all_documents
            )
            if any(
                document_id in scanned_ids
                for document_id in group
            )
        )
        duplicate_ids = defaultdict(set)

        for group in duplicate_groups:
            for document_id in group:
                duplicate_ids[document_id].update(
                    candidate
                    for candidate in group
                    if candidate != document_id
                )

        decorated = tuple(
            SourceRegistrationItem(
                document_id=item.document_id,
                path_key=item.path_key,
                action=item.action,
                content_hash=item.content_hash,
                duplicate_candidate_ids=tuple(
                    sorted(
                        duplicate_ids[
                            item.document_id
                        ]
                    )
                ),
            )
            for item in items
        )

        return SourceRegistrationResult(
            root_key=scan.root.key,
            scan_manifest_hash=scan.manifest_hash,
            items=decorated,
            missing_registry_ids=(
                self._missing_registry_ids(scan)
            ),
            duplicate_groups=duplicate_groups,
            issue_count=len(scan.issues),
            ignored_unsupported=(
                scan.ignored_unsupported
            ),
            ignored_symlinks=scan.ignored_symlinks,
        )
