"""Read-only Phase 5.5 legacy Resources 2 reconciliation/candidate preview."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from personal_learning_assistant.domain.resources2_models import (
    CandidateResource,
    LegacyResourceDecision,
    ResourceReconciliationReport,
)
from personal_learning_assistant.repositories.sqlite.resources2_repository import (
    SQLiteResources2Repository,
)
from personal_learning_assistant.services.resources2_service import (
    Resources2Service,
    normalize_canonical_uri,
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _suggest_type(kind: str, path_key: str) -> str:
    lower = (str(path_key or "") + " " + str(kind or "")).casefold()
    if "transcript" in lower or lower.endswith(".vtt") or lower.endswith(".srt"):
        return "youtube_lecture"
    if "problem" in lower or "assignment" in lower or "pset" in lower:
        return "problem_set"
    if "textbook" in lower or "book" in lower:
        return "textbook"
    if "pdf" in lower:
        return "pdf"
    if "markdown" in lower or lower.endswith(".md"):
        return "course_notes"
    return "other"


def _title_from_identity(path_key: Optional[str], canonical_uri: Optional[str], fallback: str) -> str:
    identity = str(path_key or canonical_uri or "").strip().rstrip("/")
    if identity:
        leaf = identity.replace("\\", "/").split("/")[-1]
        if leaf:
            return leaf
    return fallback


def reconcile_legacy_resources(
    path,
    repository: SQLiteResources2Repository,
) -> ResourceReconciliationReport:
    source = Path(path)
    if not source.exists():
        raw = b""
        source_status = "missing"
        parsed = None
    else:
        raw = source.read_bytes()
        if not raw.strip():
            source_status = "empty_file"
            parsed = None
        else:
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
                source_status = "invalid_json"
            else:
                source_status = "valid_list" if isinstance(parsed, list) else "wrong_shape"

    service = Resources2Service(repository)
    decisions = []
    valid_count = 0
    if isinstance(parsed, list):
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                decisions.append(
                    LegacyResourceDecision(
                        legacy_index=index,
                        title="",
                        decision="needs_review",
                        candidate_resource_ids=(),
                        reason="legacy row is not an object",
                    )
                )
                continue
            valid_count += 1
            title = str(item.get("title") or "").strip()
            resource_type = str(item.get("type") or "other").strip() or "other"
            link = str(item.get("link") or "").strip()
            if not title or not link:
                decisions.append(
                    LegacyResourceDecision(
                        legacy_index=index,
                        title=title,
                        decision="needs_review",
                        candidate_resource_ids=(),
                        reason="legacy row lacks title or link identity",
                    )
                )
                continue
            candidates = service.get_duplicate_candidates(
                title=title,
                canonical_uri=link,
                provider="",
                external_id=None,
            )
            if candidates:
                decisions.append(
                    LegacyResourceDecision(
                        legacy_index=index,
                        title=title,
                        decision="match_existing",
                        candidate_resource_ids=tuple(
                            candidate.resource_id for candidate in candidates
                        ),
                        reason="canonical identity/title candidate already exists",
                    )
                )
            else:
                decisions.append(
                    LegacyResourceDecision(
                        legacy_index=index,
                        title=title,
                        decision="create_resource",
                        candidate_resource_ids=(),
                        reason="validated legacy row has no existing candidate",
                    )
                )

    document_candidates = []
    for row in repository.unlinked_documents():
        document_id = str(row[0])
        kind = str(row[1])
        canonical_uri = None if row[2] is None else str(row[2])
        path_key = None if row[3] is None else str(row[3])
        content_hash = str(row[4])
        duplicate_ids = tuple(
            item.resource_id
            for item in repository.duplicate_candidates(
                canonical_uri=normalize_canonical_uri(canonical_uri),
                provider="",
                external_id=None,
                document_ids=(document_id,),
            )
        )
        document_candidates.append(
            CandidateResource(
                source_kind="document",
                source_id=document_id,
                suggested_type=_suggest_type(kind, path_key or canonical_uri or ""),
                suggested_title=_title_from_identity(
                    path_key, canonical_uri, "Registered document"
                ),
                identity_hint="content_hash:" + content_hash,
                duplicate_resource_ids=duplicate_ids,
            )
        )

    note_candidates = []
    for row in repository.unlinked_notes():
        note_id = str(row[0])
        title = str(row[1])
        path_key = str(row[2])
        note_type = str(row[3])
        # Notes are candidates only. A later explicit user action decides
        # whether the note should also become a learning resource.
        note_candidates.append(
            CandidateResource(
                source_kind="note",
                source_id=note_id,
                suggested_type="course_notes",
                suggested_title=title,
                identity_hint="note:" + path_key,
                duplicate_resource_ids=(),
            )
        )

    return ResourceReconciliationReport(
        source_status=source_status,
        source_sha256=_sha256(raw),
        source_byte_count=len(raw),
        validated_legacy_records=valid_count,
        legacy_decisions=tuple(decisions),
        document_candidates=tuple(document_candidates),
        note_candidates=tuple(note_candidates),
    )
