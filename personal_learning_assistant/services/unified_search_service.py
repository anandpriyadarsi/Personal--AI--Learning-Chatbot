"""Student-facing Unified Study Search over retrieval, vault search, and metadata."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sqlite3
from urllib.parse import quote

from personal_learning_assistant.domain.study_search_models import (
    SearchSuggestion,
    StudySearchResult,
)
from personal_learning_assistant.repositories.sqlite.search_metadata_repository import (
    SQLiteSearchMetadataRepository,
)
from personal_learning_assistant.repositories.sqlite.study_interaction_repository import (
    SQLiteStudyInteractionRepository,
)
from personal_learning_assistant.services.study_interaction_service import (
    StudyInteractionService,
)
from personal_learning_assistant.services.study_item_resolver import obsidian_identity
from personal_learning_assistant.services.unified_search_runtime import (
    UnifiedSearchStaleIndexError,
    get_unified_search_runtime,
)


class UnifiedSearchError(RuntimeError):
    pass


def _open_ro(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise UnifiedSearchError("academic database is unavailable")
    uri = "file:{}?mode=ro".format(
        quote(str(path.resolve()).replace("\\", "/"), safe="/:")
    )
    con = sqlite3.connect(uri, uri=True, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _snippet(value, limit=360):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class UnifiedSearchService:
    def __init__(
        self,
        *,
        database_path="data/learning_assistant.db",
        runtime=None,
        obsidian_workspace_factory=None,
    ):
        self.database_path = Path(database_path)
        self.runtime = runtime or get_unified_search_runtime()
        self._obsidian_workspace_factory = obsidian_workspace_factory

    def _obsidian(self):
        if self._obsidian_workspace_factory is not None:
            return self._obsidian_workspace_factory()
        from personal_learning_assistant.services.obsidian_workspace_service import (
            build_obsidian_workspace_service,
        )
        return build_obsidian_workspace_service()

    def filter_options(self):
        con = _open_ro(self.database_path)
        try:
            return SQLiteSearchMetadataRepository(con).filter_options()
        finally:
            con.close()

    def suggest(self, query, *, limit=8):
        clean = " ".join(str(query or "").split())[:200]
        if len(clean) < 2:
            return ()
        con = _open_ro(self.database_path)
        try:
            repo = SQLiteSearchMetadataRepository(con)
            results = []
            try:
                vault = self._obsidian().workspace(clean)
                for note in tuple(vault.get("notes", ()) or ())[: int(limit)]:
                    path = str(note.get("relative_path") or "")
                    results.append(
                        SearchSuggestion(
                            kind="obsidian_note",
                            label=str(note.get("title") or path),
                            subtitle="Obsidian note",
                            value=str(note.get("title") or path),
                            open_target="/obsidian/note?path={}".format(
                                quote(path, safe="")
                            ),
                        )
                    )
            except Exception:
                pass
            for kind, label, subtitle in repo.metadata_suggestions(clean, limit=limit):
                results.append(
                    SearchSuggestion(
                        kind=kind,
                        label=label,
                        subtitle=subtitle,
                        value=label,
                    )
                )
            return tuple(results[: int(limit)])
        finally:
            con.close()

    def _obsidian_results(self, query, interaction, *, limit):
        results = []
        try:
            workspace = self._obsidian().workspace(query)
            for row in tuple(workspace.get("notes", ()) or ())[: int(limit)]:
                path = str(row.get("relative_path") or "").strip()
                if not path:
                    continue
                note = self._obsidian().note_preview(path)
                identity = obsidian_identity(note)
                history = interaction.history(identity)
                excerpt = (
                    row.get("excerpt")
                    or row.get("snippet")
                    or note.get("text")
                    or ""
                )
                results.append(
                    StudySearchResult(
                        item_kind="obsidian_note",
                        item_id=identity.item_id,
                        version_hash=identity.version_hash,
                        title=str(note.get("title") or path),
                        subtitle="Obsidian · {}".format(path),
                        source_label="Obsidian Note",
                        snippet=_snippet(excerpt),
                        open_target="/obsidian/note?path={}".format(
                            quote(path, safe="")
                        ),
                        relevance_reasons=("Vault text/title match",),
                        times_opened=history["times_opened"],
                        total_active_seconds=history["total_active_seconds"],
                        last_read_at=history["last_read_at"],
                    )
                )
        except Exception:
            return ()
        return tuple(results)

    def search(
        self,
        query,
        *,
        course_ids=(),
        topic_ids=(),
        source_types=(),
        providers=(),
        top_k=8,
    ):
        clean = " ".join(str(query or "").split())[:500]
        if not clean:
            return ()
        source_filter = {str(x).strip() for x in source_types if str(x).strip()}
        con = _open_ro(self.database_path)
        try:
            meta_repo = SQLiteSearchMetadataRepository(con)
            interaction = StudyInteractionService(
                SQLiteStudyInteractionRepository(con)
            )
            output = []
            allow_obsidian = (
                (not source_filter or "obsidian_note" in source_filter)
                and not course_ids
                and not topic_ids
                and not providers
            )
            if allow_obsidian:
                for item in self._obsidian_results(
                    clean, interaction, limit=max(3, int(top_k))
                ):
                    output.append((0.030, item))

            if not source_filter or any(
                kind in source_filter
                for kind in (
                    "knowledge_document",
                    "pdf",
                    "textbook",
                    "resource",
                    "youtube",
                    "lecture",
                    "external_lecture",
                )
            ):
                try:
                    hits = self.runtime.search(
                        clean,
                        course_ids=tuple(course_ids),
                        topic_ids=tuple(topic_ids),
                        providers=tuple(providers),
                        top_k=max(12, int(top_k) * 4),
                    )
                except UnifiedSearchStaleIndexError:
                    raise
                except Exception as error:
                    raise UnifiedSearchError(
                        "study search is temporarily unavailable"
                    ) from error

                grouped = defaultdict(list)
                for hit in hits:
                    grouped[str(hit.document_id)].append(hit)
                metadata = meta_repo.documents(grouped)
                query_fold = clean.casefold()
                for document_id, local_hits in grouped.items():
                    item = metadata.get(document_id)
                    if item is None:
                        continue
                    if (
                        source_filter
                        and "knowledge_document" not in source_filter
                        and item["source_kind"] not in source_filter
                    ):
                        continue
                    if providers and item["provider"] not in set(providers):
                        continue
                    best = local_hits[0]
                    from personal_learning_assistant.domain.study_item_models import (
                        StudyItemIdentity,
                    )
                    identity = StudyItemIdentity(
                        "knowledge_document",
                        document_id,
                        item["version_hash"],
                    )
                    history = interaction.history(identity)
                    reasons = []
                    title_fold = item["title"].casefold()
                    if title_fold == query_fold:
                        reasons.append("Exact title match")
                    elif query_fold in title_fold or title_fold in query_fold:
                        reasons.append("Strong title match")
                    if item["topic_labels"]:
                        reasons.append("Linked academic topic")
                    if best.semantic_rank is not None:
                        reasons.append("Semantic match")
                    if best.lexical_rank is not None:
                        reasons.append("Text match")
                    if history["times_opened"]:
                        reasons.append("Studied before")
                    output.append(
                        (
                            float(best.score)
                            + (
                                0.025
                                if reasons and reasons[0] == "Exact title match"
                                else 0
                            )
                            + min(history["times_opened"], 3) * 0.0005,
                            StudySearchResult(
                                item_kind="knowledge_document",
                                item_id=document_id,
                                version_hash=item["version_hash"],
                                title=item["title"],
                                subtitle=" · ".join(
                                    item["course_labels"][:1]
                                    + item["topic_labels"][:1]
                                ),
                                source_label=item["source_label"],
                                snippet=_snippet(best.text),
                                course_ids=item["course_ids"],
                                course_labels=item["course_labels"],
                                topic_ids=item["topic_ids"],
                                topic_labels=item["topic_labels"],
                                provider=item["provider"],
                                open_target="/knowledge/item/{}".format(
                                    quote(document_id, safe="")
                                ),
                                matched_chunk_ids=tuple(
                                    str(hit.chunk_id) for hit in local_hits
                                ),
                                page_numbers=tuple(
                                    sorted(
                                        {
                                            int(hit.page_number)
                                            for hit in local_hits
                                            if hit.page_number is not None
                                        }
                                    )
                                ),
                                relevance_reasons=tuple(dict.fromkeys(reasons)),
                                times_opened=history["times_opened"],
                                total_active_seconds=history["total_active_seconds"],
                                last_read_at=history["last_read_at"],
                            ),
                        )
                    )

            output.sort(
                key=lambda pair: (
                    -pair[0],
                    pair[1].title.casefold(),
                    pair[1].item_id,
                )
            )
            return tuple(item for _score, item in output[: int(top_k)])
        finally:
            con.close()


def build_unified_search_service():
    return UnifiedSearchService()
