"""Phase 6.9 final Tutor Workspace reconciliation and closure."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from personal_learning_assistant.migration.authority_promotion import (
    BACKEND_SQLITE,
    read_authority_control,
)
from personal_learning_assistant.retrieval.index_store import RetrievalIndexStore
from personal_learning_assistant.services.retrieval_service import RetrievalService


class Phase6ClosureError(RuntimeError):
    pass


_REQUIRED_TABLES = {
    "courses",
    "topics",
    "resources",
    "assessments",
    "questions",
    "question_topic_mappings",
    "question_sources",
    "question_attempts",
    "mistake_events",
    "study_sessions",
    "knowledge_documents",
    "knowledge_chunks",
    "operation_journal",
    "outbox_events",
    "tutor_sessions",
    "tutor_turns",
    "tutor_evidence_links",
    "tutor_feedback",
    "practice_sessions",
    "practice_items",
    "practice_item_sources",
    "practice_attempts",
}


class Phase6ClosureService:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        authority_control_path,
        index_root,
        workspace_service,
        retrieval_probe=None,
    ):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be an explicit sqlite3.Connection")
        self.connection = connection
        self.connection.row_factory = sqlite3.Row
        self.authority_control_path = Path(authority_control_path)
        self.index_root = Path(index_root)
        self.workspace_service = workspace_service
        self.retrieval_probe = retrieval_probe

    def verify(
        self,
        course_code: str,
        *,
        as_of,
        target_assessment_id=None,
        smoke_query="LU factorization triangular matrices",
    ):
        issues = []
        report = {}

        self._verify_authority(report, issues)
        self._verify_schema(report, issues)
        self._verify_tutor_evidence(report, issues)
        self._verify_practice(report, issues)
        self._verify_lecture_state(report, issues)
        self._verify_agent_audit(report, issues)

        workspace = self.workspace_service.snapshot(
            course_code,
            as_of=as_of,
            target_assessment_id=target_assessment_id,
            limit_topics=5,
            max_actions=10,
            recent_limit=12,
        )
        report["workspace"] = {
            "course_id": workspace.course_id,
            "course_code": workspace.course_code,
            "course_name": workspace.course_name,
            "as_of": workspace.as_of,
            "tutor_schema_ready": workspace.tutor_schema_ready,
            "practice_schema_ready": workspace.practice_schema_ready,
            "topic_count": workspace.counts.topic_count,
            "mentor_topic_count": len(workspace.mentor.topics),
            "mentor_action_count": len(workspace.mentor.actions),
            "recent_activity_count": len(workspace.recent_activity),
            "writes_performed": workspace.writes_performed,
            "provider_called": workspace.provider_called,
        }
        if not workspace.tutor_schema_ready:
            issues.append("Tutor Workspace reports migration 0003 unavailable")
        if not workspace.practice_schema_ready:
            issues.append("Tutor Workspace reports migration 0004 unavailable")
        if workspace.writes_performed or workspace.provider_called:
            issues.append("Tutor Workspace preview was not purely read-only")
        if (
            workspace.mentor.writes_performed
            or workspace.mentor.llm_called
            or workspace.mentor.authoritative_state_changes
        ):
            issues.append(
                "Adaptive Mentor violated read-only/advisory closure boundary"
            )

        retrieval = self._verify_retrieval(
            workspace.course_id,
            smoke_query=smoke_query,
            issues=issues,
        )
        report["retrieval"] = retrieval

        report["issue_count"] = len(issues)
        report["issues"] = tuple(issues)
        if issues:
            raise Phase6ClosureError(
                "Phase 6 closure reconciliation failed:\n- {}".format(
                    "\n- ".join(issues)
                )
            )
        return report

    def _verify_authority(self, report, issues):
        try:
            state = read_authority_control(self.authority_control_path)
        except Exception as error:
            issues.append(
                "authority control could not be read: {}".format(error)
            )
            report["authority"] = {"readable": False}
            return

        sqlite_authoritative = (
            state.storage_backend == BACKEND_SQLITE
            and bool(state.legacy_writes_blocked)
        )
        if not sqlite_authoritative:
            issues.append(
                "SQLite is not the locked structured authority with legacy writes blocked"
            )
        report["authority"] = {
            "readable": True,
            "storage_backend": state.storage_backend,
            "legacy_writes_blocked": bool(state.legacy_writes_blocked),
            "sqlite_authoritative": sqlite_authoritative,
        }

    def _verify_schema(self, report, issues):
        integrity = str(
            self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        )
        foreign_keys = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if integrity != "ok":
            issues.append(
                "PRAGMA integrity_check returned {!r}".format(integrity)
            )
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
            ).fetchall()
        )
        if len(versions) < 4 or versions[:4] != (1, 2, 3, 4):
            issues.append(
                "unexpected migration history {}; Phase 6 closure requires "
                "intact 0001/0002/0003/0004 prefix".format(versions)
            )

        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            issues.append(
                "required Phase 6 table(s) missing: {}".format(
                    ", ".join(missing)
                )
            )

        report["schema"] = {
            "integrity_check": integrity,
            "foreign_key_violation_count": len(foreign_keys),
            "migration_versions": versions,
            "missing_required_tables": tuple(missing),
        }

    def _verify_tutor_evidence(self, report, issues):
        document_mismatch = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM tutor_evidence_links tel "
                "JOIN knowledge_chunks kc ON kc.id=tel.chunk_id "
                "WHERE tel.document_id<>kc.document_id"
            ).fetchone()[0]
        )
        unsupported = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM tutor_turns tt "
                "WHERE tt.role='assistant' "
                "AND tt.support_level IN ('grounded','mixed') "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM tutor_evidence_links tel "
                "  WHERE tel.turn_id=tt.id"
                ")"
            ).fetchone()[0]
        )
        user_evidence = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM tutor_evidence_links tel "
                "JOIN tutor_turns tt ON tt.id=tel.turn_id "
                "WHERE tt.role='user'"
            ).fetchone()[0]
        )
        if document_mismatch:
            issues.append(
                "{} tutor evidence link(s) point at a document different "
                "from the cited chunk".format(document_mismatch)
            )
        if unsupported:
            issues.append(
                "{} grounded/mixed assistant turn(s) lack exact chunk evidence".format(
                    unsupported
                )
            )
        if user_evidence:
            issues.append(
                "{} user turn(s) unexpectedly own tutor evidence links".format(
                    user_evidence
                )
            )
        report["tutor_evidence"] = {
            "chunk_document_mismatch_count": document_mismatch,
            "grounded_turn_without_evidence_count": unsupported,
            "user_turn_evidence_link_count": user_evidence,
            "session_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM tutor_sessions"
                ).fetchone()[0]
            ),
            "assistant_turn_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM tutor_turns WHERE role='assistant'"
                ).fetchone()[0]
            ),
        }

    def _verify_practice(self, report, issues):
        source_mismatch = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM practice_item_sources pis "
                "JOIN knowledge_chunks kc ON kc.id=pis.chunk_id "
                "WHERE pis.document_id<>kc.document_id"
            ).fetchone()[0]
        )
        item_without_source = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM practice_items pi "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM practice_item_sources pis "
                "  WHERE pis.item_id=pi.id"
                ")"
            ).fetchone()[0]
        )
        if source_mismatch:
            issues.append(
                "{} practice source link(s) have chunk/document mismatch".format(
                    source_mismatch
                )
            )
        if item_without_source:
            issues.append(
                "{} persisted practice item(s) have no exact source chunk".format(
                    item_without_source
                )
            )
        report["practice"] = {
            "chunk_document_mismatch_count": source_mismatch,
            "item_without_source_count": item_without_source,
            "session_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM practice_sessions"
                ).fetchone()[0]
            ),
            "deterministic_attempt_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM practice_attempts "
                    "WHERE grading_mode='deterministic'"
                ).fetchone()[0]
            ),
            "advisory_attempt_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM practice_attempts "
                    "WHERE grading_mode='advisory'"
                ).fetchone()[0]
            ),
        }

    def _verify_lecture_state(self, report, issues):
        duplicate_open = self.connection.execute(
            "SELECT resource_id,COUNT(*) AS n FROM study_sessions "
            "WHERE ended_at IS NULL AND resource_id IS NOT NULL "
            "GROUP BY resource_id HAVING COUNT(*)>1"
        ).fetchall()
        if duplicate_open:
            issues.append(
                "{} resource(s) have multiple simultaneously open study-session "
                "segments".format(len(duplicate_open))
            )
        report["lecture_learning"] = {
            "open_segment_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM study_sessions WHERE ended_at IS NULL "
                    "AND resource_id IS NOT NULL"
                ).fetchone()[0]
            ),
            "duplicate_open_resource_count": len(duplicate_open),
        }

    def _verify_agent_audit(self, report, issues):
        planned = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM operation_journal "
                "WHERE kind='academic_agent_action' AND state='planned'"
            ).fetchone()[0]
        )
        duplicate_completed = self.connection.execute(
            "SELECT target_path,COUNT(*) AS n FROM operation_journal "
            "WHERE kind='academic_agent_action' AND state='completed' "
            "GROUP BY target_path HAVING COUNT(*)>1"
        ).fetchall()
        missing_event = int(
            self.connection.execute(
                "SELECT COUNT(*) FROM operation_journal oj "
                "WHERE oj.kind='academic_agent_action' AND oj.state='completed' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM outbox_events oe "
                "  WHERE oe.event_type='academic_agent.action_executed' "
                "  AND oe.entity_type='agent_action' "
                "  AND oe.entity_id=oj.target_path"
                ")"
            ).fetchone()[0]
        )
        invalid_payload = 0
        for row in self.connection.execute(
            "SELECT payload_json FROM outbox_events "
            "WHERE event_type='academic_agent.action_executed' "
            "AND entity_type='agent_action'"
        ).fetchall():
            try:
                payload = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                invalid_payload += 1
                continue
            if not isinstance(payload, dict) or not payload.get("fingerprint"):
                invalid_payload += 1

        if planned:
            issues.append(
                "{} academic-agent action claim(s) remain planned; inspect before "
                "closing Phase 6".format(planned)
            )
        if duplicate_completed:
            issues.append(
                "{} academic-agent fingerprint(s) were completed more than once".format(
                    len(duplicate_completed)
                )
            )
        if missing_event:
            issues.append(
                "{} completed academic-agent action(s) lack execution outbox evidence".format(
                    missing_event
                )
            )
        if invalid_payload:
            issues.append(
                "{} academic-agent execution event(s) have invalid audit payload".format(
                    invalid_payload
                )
            )

        report["academic_agent"] = {
            "planned_action_count": planned,
            "completed_action_count": int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM operation_journal "
                    "WHERE kind='academic_agent_action' AND state='completed'"
                ).fetchone()[0]
            ),
            "duplicate_completed_fingerprint_count": len(duplicate_completed),
            "completed_without_outbox_count": missing_event,
            "invalid_execution_payload_count": invalid_payload,
        }

    def _verify_retrieval(self, course_id, *, smoke_query, issues):
        if self.retrieval_probe is not None:
            result = dict(self.retrieval_probe(course_id, smoke_query))
            if int(result.get("hit_count", 0)) <= 0:
                issues.append("retrieval smoke probe returned no course-grounded hit")
            return result

        store = None
        try:
            store = RetrievalIndexStore(self.index_root)
            service = RetrievalService(store)
            hits = service.search(
                smoke_query,
                course_ids=(course_id,),
                top_k=5,
            )
            result = {
                "generation_id": str(store.manifest.get("generation_id", "")),
                "source_fingerprint": str(
                    store.manifest.get("source_fingerprint", "")
                ),
                "lexical_backend": str(
                    store.manifest.get("lexical_backend", "")
                ),
                "semantic_enabled": bool(
                    store.manifest.get("semantic_enabled", False)
                ),
                "hit_count": len(hits),
                "hit_chunk_ids": tuple(hit.chunk_id for hit in hits),
            }
            if not hits:
                issues.append(
                    "current retrieval generation returned no MA103N smoke-query hit"
                )
            return result
        except Exception as error:
            issues.append("current retrieval generation is unusable: {}".format(error))
            return {
                "generation_id": "",
                "hit_count": 0,
                "error": "{}: {}".format(type(error).__name__, error),
            }
        finally:
            if store is not None:
                store.close()
