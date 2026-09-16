"""Conservative Phase 7.1 legacy/compatibility candidate catalogue.

This catalogue does not declare anything safe to delete.  It supplies the known
surfaces that Phase 7 must observe and reconcile before retirement decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class CandidateSpec:
    path: str
    component_kind: str
    replacement: str
    policy: str
    note: str = ""


# Policy is deliberately conservative.  Phase 7.1 never emits
# "retirement_candidate" from static analysis alone.
KNOWN_CANDIDATES: Tuple[CandidateSpec, ...] = (
    CandidateSpec(
        "main.py",
        "legacy_entrypoint",
        "Tutor Workspace / modern CLI composition",
        "observe",
        "V13 menu still dynamically routes many historical root modules.",
    ),
    CandidateSpec("dashboard.py", "legacy_ui", "Tutor Workspace", "observe"),
    CandidateSpec("notes.py", "legacy_facade", "Notes Studio / notes CLI", "observe"),
    CandidateSpec("resources.py", "legacy_facade", "Resources 2 / resources CLI", "observe"),
    CandidateSpec("backup.py", "legacy_recovery", "Phase 7 recovery bundle", "observe"),
    CandidateSpec("knowledge.py", "legacy_knowledge", "Knowledge Registry + unified ingestion", "observe"),
    CandidateSpec("knowledge_paths.py", "legacy_path_config", "Knowledge Registry/source scanner", "observe"),
    CandidateSpec("course_manager.py", "legacy_facade", "CourseService + course CLI", "observe"),
    CandidateSpec("learning_memory.py", "legacy_facade", "SQLite learning memory/progress", "observe"),
    CandidateSpec("academic_progress.py", "legacy_engine", "SQLite learning progress + Knowledge Navigator", "observe"),
    CandidateSpec("weekly_planner.py", "legacy_planner", "SQLite study plans", "observe"),
    CandidateSpec("multi_course_planner.py", "legacy_planner", "SQLite study plans", "observe"),
    CandidateSpec("intelligent_study_planner.py", "legacy_planner", "SQLite study plans + Adaptive Mentor", "observe"),
    CandidateSpec("assignment_exam_assistant.py", "legacy_assessment_ui", "formal assessment repositories + Tutor Workspace", "observe"),
    CandidateSpec("assessment_question_workspace.py", "legacy_assessment_ui", "formal question repositories + Exam Intelligence", "observe"),
    CandidateSpec("assignment_file_importer.py", "legacy_importer_ui", "registered document ingestion", "observe"),
    CandidateSpec("automatic_topic_mapping.py", "legacy_mapping_engine", "reviewed question-topic mappings", "observe"),
    CandidateSpec("assessment_performance.py", "legacy_assessment_engine", "SQLite attempts/mistakes/performance", "observe"),
    CandidateSpec("academic_intelligence_dashboard.py", "legacy_ui", "Tutor Workspace + Adaptive Mentor", "observe"),
    CandidateSpec("semester_grade_intelligence.py", "legacy_grade_engine", "SQLite grades/calendar intelligence", "observe"),
    CandidateSpec("academic_calendar_planner.py", "legacy_calendar_engine", "SQLite academic calendar/plans", "observe"),
    CandidateSpec("daily_academic_brief.py", "legacy_ui", "Tutor Workspace + Adaptive Mentor", "observe"),
    CandidateSpec(
        "personal_academic_agent.py",
        "compatibility_entrypoint",
        "Phase 6.8 Academic Agent Cutover",
        "compatibility",
        "Historical intent-routing surface remains covered by regression tests.",
    ),
    CandidateSpec(
        "personal_learning_assistant/services/academic_agent_service.py",
        "compatibility_service",
        "Phase 6.8 Academic Agent Cutover",
        "compatibility",
        "Phase-2/V13 INTENT_LABELS compatibility service; do not remove in 7.1.",
    ),
    CandidateSpec("rag_answer.py", "legacy_rag", "Phase 5.8 retrieval + Phase 6 grounded tutor", "observe"),
    CandidateSpec("semantic_retrieval.py", "legacy_retrieval", "Phase 5.8 rebuildable retrieval", "observe"),
    CandidateSpec("hybrid_retrieval.py", "legacy_retrieval", "Phase 5.8 rebuildable retrieval", "observe"),
    CandidateSpec("obsidian_integration.py", "legacy_obsidian_ui", "Vault Registry + Notes Studio", "observe"),
    CandidateSpec("youtube_ingestion.py", "legacy_ingestion_ui", "Unified ingestion / external-course knowledge", "observe"),
    CandidateSpec("youtube_analysis.py", "legacy_analysis_ui", "External-course knowledge + grounded tutor", "observe"),
    CandidateSpec("math_document_reader.py", "legacy_extractor", "Unified ingestion adapters", "observe"),
    CandidateSpec("vision_math_reader.py", "legacy_extractor", "Unified ingestion adapters", "observe"),
)


def family_candidate(path: str):
    """Return a generated candidate for known compatibility families."""
    normalized = path.replace("\\", "/")
    if normalized.startswith("personal_learning_assistant/repositories/json/") and normalized.endswith(".py"):
        if normalized.endswith("/__init__.py"):
            return None
        name = normalized.rsplit("/", 1)[-1]
        return CandidateSpec(
            normalized,
            "legacy_json_repository",
            "SQLite repository / structured authority router",
            "compatibility",
            "Retained for compatibility/reconciliation until consumer observation is complete.",
        )
    backend_names = {
        "assessment_backend.py",
        "attempt_performance_backend.py",
        "course_backend.py",
        "grade_calendar_backend.py",
        "learning_progress_backend.py",
        "question_backend.py",
        "question_topic_backend.py",
        "study_plan_backend.py",
    }
    if normalized.startswith("personal_learning_assistant/repositories/"):
        if normalized.rsplit("/", 1)[-1] in backend_names:
            return CandidateSpec(
                normalized,
                "phase4_compatibility_backend",
                "structured_authority_router + SQLite repositories",
                "compatibility",
                "Dual-read/cutover-era compatibility surface; retain until Phase 7 evidence is complete.",
            )
    return None
