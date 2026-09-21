"""Human-facing metadata reads for Unified Study Search."""

from __future__ import annotations

import sqlite3
from typing import Iterable


class SearchMetadataRepositoryError(RuntimeError):
    pass


def _tuple(rows, key):
    return tuple(str(row[key]) for row in rows if row[key] is not None and str(row[key]).strip())


class SQLiteSearchMetadataRepository:
    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def document(self, document_id: str):
        row = self.connection.execute(
            "SELECT * FROM knowledge_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        resources = self.connection.execute(
            "SELECT r.id,r.title,r.resource_type,r.provider,r.canonical_uri "
            "FROM resource_documents rd JOIN resources r ON r.id=rd.resource_id "
            "WHERE rd.document_id=? AND r.deleted_at IS NULL "
            "ORDER BY CASE rd.role WHEN 'source' THEN 0 ELSE 1 END,r.title,r.id",
            (document_id,),
        ).fetchall()
        course_rows = self.connection.execute(
            "SELECT DISTINCT c.id,c.code,c.name "
            "FROM resource_documents rd "
            "JOIN resource_courses rc ON rc.resource_id=rd.resource_id "
            "JOIN courses c ON c.id=rc.course_id AND c.deleted_at IS NULL "
            "WHERE rd.document_id=? ORDER BY c.code,c.id",
            (document_id,),
        ).fetchall()
        topic_rows = self.connection.execute(
            "SELECT DISTINCT t.id,t.name "
            "FROM resource_documents rd "
            "JOIN resource_topics rt ON rt.resource_id=rd.resource_id "
            "JOIN topics t ON t.id=rt.topic_id AND t.deleted_at IS NULL "
            "WHERE rd.document_id=? ORDER BY t.position,t.name,t.id",
            (document_id,),
        ).fetchall()
        primary = resources[0] if resources else None
        title = (
            str(primary["title"])
            if primary is not None and str(primary["title"]).strip()
            else str(row["path_key"] or row["canonical_uri"] or document_id)
        )
        source_kind = str(
            primary["resource_type"] if primary is not None else row["kind"]
        )
        provider = str(primary["provider"] or "") if primary is not None else ""
        uri = (
            str(primary["canonical_uri"] or "")
            if primary is not None
            else str(row["canonical_uri"] or "")
        )
        return {
            "document_id": str(row["id"]),
            "version_hash": str(row["content_hash"]).lower(),
            "title": title,
            "source_kind": source_kind,
            "source_label": source_kind.replace("_", " ").title(),
            "provider": provider,
            "canonical_uri": uri,
            "course_ids": tuple(str(x["id"]) for x in course_rows),
            "course_labels": tuple(
                "{} · {}".format(x["code"], x["name"]) for x in course_rows
            ),
            "topic_ids": tuple(str(x["id"]) for x in topic_rows),
            "topic_labels": tuple(str(x["name"]) for x in topic_rows),
            "resource_ids": tuple(str(x["id"]) for x in resources),
        }

    def documents(self, document_ids: Iterable[str]):
        return {
            document_id: item
            for document_id in tuple(dict.fromkeys(str(x) for x in document_ids))
            for item in (self.document(document_id),)
            if item is not None
        }

    def note_suggestions(self, query: str, *, limit=8):
        clean = str(query or "").strip()
        if len(clean) < 2:
            return ()
        pattern = "%{}%".format(clean.replace("%", r"\%").replace("_", r"\_"))
        rows = self.connection.execute(
            "SELECT n.id,n.title,n.relative_path,n.source_hash,"
            "GROUP_CONCAT(DISTINCT t.name) AS tags "
            "FROM note_metadata n "
            "LEFT JOIN note_tags nt ON nt.note_id=n.id "
            "LEFT JOIN tags t ON t.id=nt.tag_id "
            "WHERE n.archived_at IS NULL AND n.trashed_at IS NULL "
            "AND (n.title LIKE ? ESCAPE '\\' OR n.relative_path LIKE ? ESCAPE '\\' "
            "OR EXISTS (SELECT 1 FROM note_tags nx JOIN tags tx ON tx.id=nx.tag_id "
            "WHERE nx.note_id=n.id AND tx.name LIKE ? ESCAPE '\\')) "
            "GROUP BY n.id ORDER BY "
            "CASE WHEN lower(n.title)=lower(?) THEN 0 "
            "WHEN lower(n.title) LIKE lower(?) THEN 1 ELSE 2 END,"
            "n.title,n.id LIMIT ?",
            (pattern, pattern, pattern, clean, clean + "%", int(limit)),
        ).fetchall()
        return tuple(
            {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "relative_path": str(row["relative_path"]),
                "version_hash": str(row["source_hash"]).lower(),
                "tags": tuple(
                    item for item in str(row["tags"] or "").split(",") if item
                ),
            }
            for row in rows
        )

    def metadata_suggestions(self, query: str, *, limit=10):
        clean = str(query or "").strip()
        if len(clean) < 2:
            return ()
        pattern = "%{}%".format(clean.replace("%", r"\%").replace("_", r"\_"))
        results = []
        for row in self.connection.execute(
            "SELECT code,name FROM courses WHERE deleted_at IS NULL "
            "AND (code LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\') "
            "ORDER BY code LIMIT ?",
            (pattern, pattern, int(limit)),
        ).fetchall():
            results.append(("course", str(row["code"]), str(row["name"])))
        for row in self.connection.execute(
            "SELECT name FROM topics WHERE deleted_at IS NULL "
            "AND name LIKE ? ESCAPE '\\' ORDER BY name LIMIT ?",
            (pattern, int(limit)),
        ).fetchall():
            results.append(("topic", str(row["name"]), "Academic topic"))
        for row in self.connection.execute(
            "SELECT title,resource_type,provider FROM resources "
            "WHERE deleted_at IS NULL AND title LIKE ? ESCAPE '\\' "
            "ORDER BY title,id LIMIT ?",
            (pattern, int(limit)),
        ).fetchall():
            subtitle = str(row["resource_type"] or "Resource").replace("_", " ").title()
            provider = str(row["provider"] or "").strip()
            if provider:
                subtitle = "{} · {}".format(subtitle, provider)
            results.append(("resource", str(row["title"]), subtitle))
        return tuple(results[: int(limit)])

    def evidence_locator(self, chunk_id: str):
        row = self.connection.execute(
            "SELECT document_id,ordinal,page_number FROM knowledge_chunks WHERE id=?",
            (str(chunk_id or "").strip(),),
        ).fetchone()
        if row is None:
            return {"document_id": "", "locator_label": ""}
        if row["page_number"] is not None:
            label = "Page {}".format(int(row["page_number"]))
        else:
            label = "Chunk {}".format(int(row["ordinal"]) + 1)
        return {
            "document_id": str(row["document_id"]),
            "locator_label": label,
        }

    def filter_options(self):
        courses = tuple(
            {
                "id": str(row["id"]),
                "code": str(row["code"]),
                "name": str(row["name"]),
            }
            for row in self.connection.execute(
                "SELECT id,code,name FROM courses "
                "WHERE deleted_at IS NULL ORDER BY code,id"
            ).fetchall()
        )
        topics = tuple(
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "course_id": str(row["course_id"]),
            }
            for row in self.connection.execute(
                "SELECT id,name,course_id FROM topics "
                "WHERE deleted_at IS NULL ORDER BY course_id,position,name,id"
            ).fetchall()
        )
        providers = tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT provider FROM resources "
                "WHERE deleted_at IS NULL AND trim(provider)<>'' "
                "ORDER BY provider"
            ).fetchall()
        )
        source_types = tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT DISTINCT resource_type FROM resources "
                "WHERE deleted_at IS NULL AND trim(resource_type)<>'' "
                "ORDER BY resource_type"
            ).fetchall()
        )
        return {
            "courses": courses,
            "topics": topics,
            "providers": providers,
            "source_types": tuple(
                dict.fromkeys(("obsidian_note", "knowledge_document") + source_types)
            ),
        }

    def document_chunks(self, document_id: str):
        row = self.connection.execute(
            "SELECT extraction_version FROM knowledge_documents WHERE id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            return ()
        version = str(row["extraction_version"] or "")
        return tuple(
            self.connection.execute(
                "SELECT id,ordinal,page_number,chunk_type,chunk_text "
                "FROM knowledge_chunks WHERE document_id=? "
                "AND extraction_version=? AND chunk_text IS NOT NULL "
                "ORDER BY ordinal,id",
                (document_id, version),
            ).fetchall()
        )
