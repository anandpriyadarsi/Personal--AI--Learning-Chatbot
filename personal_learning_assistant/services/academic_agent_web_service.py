"""Lazy Phase 7.5.9 browser adapter for the Academic Agent workspace.

The web adapter composes existing Phase 5/6 read/tutor boundaries. Mentor reads
are advisory only. The only production writes permitted through this service are
existing tutor session, turn, and evidence rows.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from personal_learning_assistant.tutor.adaptive_state import load_adaptive_state
import sqlite3
from urllib.parse import quote


TUTOR_MODES = (
    "concept",
    "doubt",
    "summary",
    "exam",
    "lecture",
    "revision",
    "guidance",
    "free",
)
SOURCE_POLICIES = ("source_only", "source_first")


class AcademicAgentWebError(RuntimeError):
    pass


class AcademicAgentWebValidationError(AcademicAgentWebError):
    pass


class AcademicAgentWebNotFoundError(AcademicAgentWebError):
    pass


class AcademicAgentWebUnavailableError(AcademicAgentWebError):
    pass


def _open_database(path, *, writable):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise AcademicAgentWebUnavailableError(
            "Academic Agent storage is temporarily unavailable."
        )
    uri = "file:{}?mode={}".format(
        quote(str(path.resolve(strict=False)).replace("\\", "/"), safe="/:"),
        "rw" if writable else "ro",
    )
    try:
        connection = sqlite3.connect(
            uri,
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
    except sqlite3.Error as error:
        raise AcademicAgentWebUnavailableError(
            "Academic Agent storage is temporarily unavailable."
        ) from error
    connection.row_factory = sqlite3.Row
    connection.execute ("PRAGMA foreign_keys=ON")
    return connection


def _session_summary(session):
    return {
        "session_id": session.session_id,
        "course_id": session.course_id,
        "mode": session.mode,
        "source_policy": session.source_policy,
        "status": session.status,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _evidence_view(evidence):
    return {
        "citation_label": evidence.citation_label,
        "chunk_id": evidence.chunk_id,
        "document_id": evidence.document_id,
        "relation_type": evidence.relation_type,
        "retrieval_score": evidence.retrieval_score,
    }


def _turn_view(turn):
    return {
        "turn_id": turn.turn_id,
        "ordinal": turn.ordinal,
        "role": turn.role,
        "content": turn.content,
        "support_level": turn.support_level,
        "provider_name": turn.provider_name,
        "provider_model": turn.provider_model,
        "created_at": turn.created_at,
        "evidence": [_evidence_view(item) for item in turn.evidence],
    }


def _session_view(session, turns):
    return {
        "session_id": session.session_id,
        "course_id": session.course_id,
        "topic_id": session.topic_id,
        "assessment_id": session.assessment_id,
        "resource_id": session.resource_id,
        "mode": session.mode,
        "source_policy": session.source_policy,
        "status": session.status,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "completed_at": session.completed_at,
        "metadata": dict(session.metadata or {}),
        "adaptive_state": load_adaptive_state(session.metadata),
        "prefill_question": str(
            dict(session.metadata or {}).get("prefill_question") or ""
        ),
        "turns": [_turn_view(turn) for turn in turns],
    }


def _scope_labels(catalogue, session, canonical_course=None):
    labels = {
        "course_label": "All courses",
        "topic_label": "",
        "assessment_label": "",
        "resource_label": "",
    }
    courses = list(dict(catalogue or {}).get("courses", ()) or ())
    canonical = dict(canonical_course or {})

    selected = None
    if canonical:
        code = str(canonical.get("code") or "").strip()
        name = str(canonical.get("name") or "").strip()
        labels["course_label"] = " · ".join(part for part in (code, name) if part)
        if code:
            selected = next(
                (
                    item for item in courses
                    if str(item.get("code") or "").strip().casefold()
                    == code.casefold()
                ),
                None,
            )
    if selected is None:
        selected = next(
            (
                item for item in courses
                if str(item.get("id") or "") == str(session.course_id or "")
            ),
            None,
        )
        if selected is not None and labels["course_label"] == "All courses":
            code = str(selected.get("code") or "").strip()
            name = str(selected.get("name") or "").strip()
            labels["course_label"] = " · ".join(
                part for part in (code, name) if part
            )

    if selected is not None and session.topic_id:
        topic = next(
            (
                item for item in list(selected.get("topics", ()) or ())
                if str(item.get("id") or item.get("topic_id") or "")
                == str(session.topic_id)
            ),
            None,
        )
        if topic is not None:
            labels["topic_label"] = str(
                topic.get("name") or topic.get("topic_name") or ""
            ).strip()
    return labels


def _mentor_view(report):
    return {
        "course_id": report.course_id,
        "course_code": report.course_code,
        "course_name": report.course_name,
        "as_of": report.as_of,
        "target_assessment_id": report.target_assessment_id,
        "target_assessment_title": report.target_assessment_title,
        "practice_history_available": report.practice_history_available,
        "llm_called": report.llm_called,
        "writes_performed": report.writes_performed,
        "authoritative_state_changes": report.authoritative_state_changes,
        "topics": [
            {
                "topic_id": topic.topic_id,
                "topic_name": topic.topic_name,
                "status": topic.status,
                "confidence": topic.confidence,
                "navigator_priority_score": topic.navigator_priority_score,
                "exam_priority_score": topic.exam_priority_score,
                "combined_priority_score": topic.combined_priority_score,
                "unresolved_mistake_count": topic.unresolved_mistake_count,
                "active_memory_count": topic.active_memory_count,
                "upcoming_assessment_count": topic.upcoming_assessment_count,
                "target_assessment_in_scope": topic.target_assessment_in_scope,
                "reasons": list(topic.reasons),
            }
            for topic in report.topics
        ],
        "actions": [
            {
                "sequence": action.sequence,
                "action_type": action.action_type,
                "topic_id": action.topic_id,
                "topic_name": action.topic_name,
                "title": action.title,
                "priority_score": action.priority_score,
                "reasons": list(action.reasons),
                "resource_id": action.resource_id,
                "question_id": action.question_id,
                "assessment_id": action.assessment_id,
                "source_labels": list(action.source_labels),
                "advisory": action.advisory,
            }
            for action in report.actions
        ],
    }


class AcademicAgentWebService:
    def __init__(
        self,
        *,
        database_path="data/learning_assistant.db",
        index_root=".phase5_retrieval",
        course_catalogue_loader=None,
        provider_factory=None,
        retrieval_service_factory=None,
    ):
        self.database_path = Path(database_path)
        self.index_root = Path(index_root)
        self._course_catalogue_loader = course_catalogue_loader
        self._provider_factory = provider_factory
        self._retrieval_service_factory = retrieval_service_factory

    def _course_catalogue(self):
        loader = self._course_catalogue_loader
        if loader is None:
            module = import_module(
                "personal_learning_assistant.services.course_dashboard_service"
            )
            loader = module.load_course_catalogue
        catalogue = loader()
        if not isinstance(catalogue, dict):
            raise AcademicAgentWebUnavailableError(
                "Course catalogue is temporarily unavailable."
            )
        return catalogue

    def _provider(self):
        factory = self._provider_factory
        if factory is None:
            module = import_module("personal_learning_assistant.tutor.http_provider")
            factory = module.OpenAICompatibleTutorProvider
        return factory()

    def _retrieval(self):
        if self._retrieval_service_factory is not None:
            return self._retrieval_service_factory(self.index_root), None
        runtime_module = import_module(
            "personal_learning_assistant.services.unified_search_runtime"
        )
        # Tutor requests run inside Flask worker threads. Do not reuse the
        # application-global retrieval runtime here because its SQLite index
        # connection is thread-affine. Create a request-local runtime and let
        # ask() close it in its existing finally block.
        runtime = runtime_module.UnifiedSearchRuntime(
            database_path=self.database_path,
            index_root=self.index_root,
        )
        return runtime, runtime

    def workspace(self, course_code=""):
        selected_course_code = str(course_code or "").strip()
        catalogue = self._course_catalogue()
        courses = list(catalogue.get("courses", ()) or ())
        provider_configured = bool(getattr(self._provider(), "configured", False))
        connection = _open_database(self.database_path, writable=False)
        try:
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = [
                _session_summary(item)
                for item in repository.list_sessions(limit=20)
            ]

            mentor = None
            message = ""
            if selected_course_code:
                selected = next(
                    (
                        item
                        for item in courses
                        if str(item.get("code", "")).casefold()
                        == selected_course_code.casefold()
                    ),
                    None,
                )
                if selected is None:
                    message = "The selected course was not found."
                else:
                    navigator_module = import_module(
                        "personal_learning_assistant.services.knowledge_navigator_service"
                    )
                    exam_module = import_module(
                        "personal_learning_assistant.services.exam_intelligence_service"
                    )
                    mentor_module = import_module(
                        "personal_learning_assistant.services.adaptive_mentor_service"
                    )
                    navigator_repo_module = import_module(
                        "personal_learning_assistant.repositories.sqlite.knowledge_navigator_repository"
                    )
                    exam_repo_module = import_module(
                        "personal_learning_assistant.repositories.sqlite.exam_intelligence_repository"
                    )
                    mentor_repo_module = import_module(
                        "personal_learning_assistant.repositories.sqlite.adaptive_mentor_repository"
                    )
                    navigator = navigator_module.KnowledgeNavigatorService(
                        navigator_repo_module.SQLiteKnowledgeNavigatorRepository(
                            connection
                        )
                    )
                    exam = exam_module.ExamIntelligenceService(
                        exam_repo_module.SQLiteExamIntelligenceRepository(connection)
                    )
                    report = mentor_module.AdaptiveMentorService(
                        navigator_service=navigator,
                        exam_intelligence_service=exam,
                        evidence_repository=(
                            mentor_repo_module.SQLiteAdaptiveMentorRepository(
                                connection
                            )
                        ),
                    ).advise(str(selected.get("code", selected_course_code)))
                    mentor = _mentor_view(report)

            return {
                "available": True,
                "message": message,
                "provider_configured": provider_configured,
                "courses": courses,
                "selected_course_code": selected_course_code,
                "mentor": mentor,
                "sessions": sessions,
                "modes": list(TUTOR_MODES),
                "source_policies": list(SOURCE_POLICIES),
            }
        finally:
            connection.close()

    def create_session(
        self,
        *,
        course_id,
        mode="concept",
        source_policy="source_only",
        title="",
    ):
        connection = _open_database(self.database_path, writable=True)
        try:
            models_module = import_module(
                "personal_learning_assistant.domain.tutor_models"
            )
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            service_module = import_module(
                "personal_learning_assistant.services.tutor_session_service"
            )
            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = service_module.TutorSessionService(repository)
            requested_course = str(course_id or "").strip()
            resolved_course_id = repository.resolve_course_id(
                requested_course or None
            )
            if requested_course and resolved_course_id is None:
                raise AcademicAgentWebValidationError(
                    "The selected course is not available in the canonical academic database."
                )
            spec = models_module.TutorSessionSpec(
                mode=str(mode or "concept").strip().casefold(),
                source_policy=str(source_policy or "source_only").strip().casefold(),
                course_id=resolved_course_id,
                title=str(title or "").strip(),
                metadata={"origin": "phase7.5.9_web"},
            )
            try:
                session = sessions.create_session(spec)
            except (
                ValueError,
                service_module.TutorSessionError,
                repository_module.TutorRepositoryError,
            ) as error:
                raise AcademicAgentWebValidationError(
                    "The selected tutor session settings are invalid."
                ) from error
            return session.session_id
        finally:
            connection.close()

    def create_source_session(
        self,
        *,
        document_id,
        version_hash,
        prefill_question="",
    ):
        clean_document_id = str(document_id or "").strip()
        clean_hash = str(version_hash or "").strip().lower()
        connection = _open_database(self.database_path, writable=True)
        try:
            metadata_module = import_module(
                "personal_learning_assistant.repositories.sqlite.search_metadata_repository"
            )
            item = metadata_module.SQLiteSearchMetadataRepository(
                connection
            ).document(clean_document_id)
            if item is None:
                raise AcademicAgentWebNotFoundError(
                    "Knowledge source was not found."
                )
            if str(item["version_hash"]).lower() != clean_hash:
                raise AcademicAgentWebValidationError(
                    "Knowledge source changed. Refresh it before asking ANVAYA."
                )
            models_module = import_module(
                "personal_learning_assistant.domain.tutor_models"
            )
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            service_module = import_module(
                "personal_learning_assistant.services.tutor_session_service"
            )
            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = service_module.TutorSessionService(repository)
            spec = models_module.TutorSessionSpec(
                mode="doubt",
                source_policy="source_only",
                course_id=(
                    item["course_ids"][0]
                    if len(item["course_ids"]) == 1
                    else None
                ),
                title="Ask ANVAYA · {}".format(item["title"]),
                metadata={
                    "origin": "phase7.5.12.2_knowledge_reader",
                    "source_document_id": clean_document_id,
                    "source_version_hash": clean_hash,
                    "source_title": item["title"],
                    "prefill_question": str(prefill_question or "").strip()[:4000],
                },
            )
            try:
                return sessions.create_session(spec).session_id
            except (
                ValueError,
                service_module.TutorSessionError,
                repository_module.TutorRepositoryError,
            ) as error:
                raise AcademicAgentWebValidationError(
                    "The source-grounded tutor session could not be created."
                ) from error
        finally:
            connection.close()

    def session_view(self, session_id):
        clean_session_id = str(session_id or "").strip()
        if not clean_session_id:
            raise AcademicAgentWebNotFoundError("Tutor session was not found.")
        connection = _open_database(self.database_path, writable=False)
        try:
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            service_module = import_module(
                "personal_learning_assistant.services.tutor_session_service"
            )
            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = service_module.TutorSessionService(repository)
            try:
                session = repository.get_session(clean_session_id)
                turns = sessions.transcript(clean_session_id)
            except repository_module.TutorRepositoryError as error:
                if "tutor session not found" in str(error).casefold():
                    raise AcademicAgentWebNotFoundError(
                        "Tutor session was not found."
                    ) from error
                raise AcademicAgentWebUnavailableError(
                    "Tutor session history is temporarily unavailable."
                ) from error
            view = _session_view(session, turns)
            canonical_course = repository.course_identity(session.course_id)
            try:
                catalogue = self._course_catalogue()
            except Exception:
                catalogue = {"courses": ()}
            view.update(
                _scope_labels(
                    catalogue,
                    session,
                    canonical_course=canonical_course,
                )
            )
            metadata_module = import_module(
                "personal_learning_assistant.repositories.sqlite.search_metadata_repository"
            )
            metadata_repo = metadata_module.SQLiteSearchMetadataRepository(connection)
            document_cache = {}
            for turn in view["turns"]:
                for evidence in turn["evidence"]:
                    document_id = evidence["document_id"]
                    if document_id not in document_cache:
                        document_cache[document_id] = metadata_repo.document(document_id)
                    metadata = document_cache[document_id]
                    locator = metadata_repo.evidence_locator(evidence["chunk_id"])
                    evidence["source_title"] = (
                        metadata["title"] if metadata is not None else ""
                    )
                    evidence["source_label"] = (
                        metadata["source_label"] if metadata is not None else "Source"
                    )
                    evidence["locator_label"] = locator["locator_label"]
            return view
        finally:
            connection.close()

    def record_feedback(self, session_id, turn_id, *, helpful):
        clean_session_id = str(session_id or "").strip()
        clean_turn_id = str(turn_id or "").strip()
        if not clean_session_id or not clean_turn_id:
            raise AcademicAgentWebValidationError("Tutor feedback target is invalid.")
        connection = _open_database(self.database_path, writable=True)
        try:
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            service_module = import_module(
                "personal_learning_assistant.services.tutor_session_service"
            )
            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = service_module.TutorSessionService(repository)
            try:
                turn = repository.get_turn(clean_turn_id)
            except repository_module.TutorRepositoryError as error:
                raise AcademicAgentWebNotFoundError(
                    "Tutor answer was not found."
                ) from error
            if str(turn.session_id) != clean_session_id or str(turn.role) != "assistant":
                raise AcademicAgentWebValidationError(
                    "Tutor feedback target is invalid."
                )
            try:
                sessions.record_feedback(
                    clean_turn_id,
                    helpful=bool(helpful),
                )
            except (
                service_module.TutorSessionError,
                repository_module.TutorRepositoryError,
            ) as error:
                raise AcademicAgentWebUnavailableError(
                    "Tutor feedback could not be saved."
                ) from error
        finally:
            connection.close()

    def ask(self, session_id, question):
        clean_question = str(question or "").strip()
        if not clean_question:
            raise AcademicAgentWebValidationError("Question cannot be empty.")

        connection = _open_database(self.database_path, writable=True)
        store = None
        try:
            repository_module = import_module(
                "personal_learning_assistant.repositories.sqlite.tutor_repository"
            )
            session_service_module = import_module(
                "personal_learning_assistant.services.tutor_session_service"
            )
            grounded_module = import_module(
                "personal_learning_assistant.services.grounded_tutor_service"
            )
            provider_module = import_module(
                "personal_learning_assistant.tutor.provider"
            )
            http_provider_module = import_module(
                "personal_learning_assistant.tutor.http_provider"
            )
            index_module = import_module(
                "personal_learning_assistant.retrieval.index_store"
            )
            grounding_module = import_module(
                "personal_learning_assistant.tutor.grounding"
            )
            runtime_module = import_module(
                "personal_learning_assistant.services.unified_search_runtime"
            )

            repository = repository_module.SQLiteTutorRepository(connection)
            sessions = session_service_module.TutorSessionService(repository)
            try:
                session = repository.get_session(str(session_id or "").strip())
            except repository_module.TutorRepositoryError as error:
                if "tutor session not found" in str(error).casefold():
                    raise AcademicAgentWebNotFoundError(
                        "Tutor session was not found."
                    ) from error
                raise AcademicAgentWebUnavailableError(
                    "Tutor session history is temporarily unavailable."
                ) from error
            if session.status != "active":
                raise AcademicAgentWebValidationError(
                    "Tutor session is not active."
                )

            try:
                retrieval, store = self._retrieval()
                provider = self._provider()
                engine = grounded_module.GroundedTutorService(
                    tutor_session_service=sessions,
                    retrieval_service=retrieval,
                    provider=provider,
                )
                engine.answer(session.session_id, clean_question)
            except runtime_module.UnifiedSearchStaleIndexError as error:
                raise AcademicAgentWebUnavailableError(
                    "Learning material changed. Rebuild the knowledge index before asking ANVAYA."
                ) from error
            except runtime_module.UnifiedSearchRuntimeError as error:
                raise AcademicAgentWebUnavailableError(
                    "Grounded academic sources are temporarily unavailable."
                ) from error
            except provider_module.TutorProviderUnavailableError as error:
                raise AcademicAgentWebUnavailableError(
                    "AI tutor is not configured on this machine."
                ) from error
            except http_provider_module.TutorProviderRequestError as error:
                raise AcademicAgentWebUnavailableError(
                    "The AI tutor could not complete this request. Your academic data was not changed."
                ) from error
            except (FileNotFoundError, index_module.RetrievalIndexError) as error:
                raise AcademicAgentWebUnavailableError(
                    "Grounded academic sources are temporarily unavailable."
                ) from error
            except (
                grounded_module.GroundedTutorError,
                grounding_module.TutorGroundingError,
            ) as error:
                raise AcademicAgentWebUnavailableError(
                    "The AI tutor could not complete this request. Your academic data was not changed."
                ) from error
        finally:
            if store is not None:
                close = getattr(store, "close", None)
                if close is not None:
                    close()
            connection.close()

        return self.session_view(session_id)


def build_academic_agent_web_service():
    return AcademicAgentWebService()
