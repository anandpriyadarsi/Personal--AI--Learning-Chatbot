"""Routes for the local Personal AI Learning Assistant web UI."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from personal_learning_assistant.repositories.json.anvaya_notes_repository import (
    AnvayaNotesConflictError,
    AnvayaNotesNotFoundError,
)
from personal_learning_assistant.services.anvaya_notes_service import (
    AnvayaNotesUnavailableError,
    AnvayaNotesValidationError,
    build_anvaya_notes_service,
)

from personal_learning_assistant.services.academic_agent_web_service import (
    AcademicAgentWebNotFoundError,
    AcademicAgentWebUnavailableError,
    AcademicAgentWebValidationError,
    build_academic_agent_web_service,
)
from personal_learning_assistant.services.assessment_dashboard_service import (
    load_assessment_catalogue,
    unavailable_assessment_catalogue,
)
from personal_learning_assistant.services.assessment_studio_service import (
    AssessmentStudioConflictError,
    AssessmentStudioNotFoundError,
    AssessmentStudioUnavailableError,
    AssessmentStudioValidationError,
    build_assessment_studio_service,
)
from personal_learning_assistant.services.assessment_package_service import (
    MAX_PACKAGE_BYTES,
    AssessmentPackageConflictError,
    AssessmentPackageNotFoundError,
    AssessmentPackageUnavailableError,
    AssessmentPackageValidationError,
    build_assessment_package_service,
)
from personal_learning_assistant.services.assessment_runner_service import (
    AssessmentRunnerConflictError,
    AssessmentRunnerNotFoundError,
    AssessmentRunnerUnavailableError,
    AssessmentRunnerValidationError,
    build_assessment_runner_service,
)
from personal_learning_assistant.services.assessment_evaluation_service import (
    MISTAKE_CATEGORIES,
    AssessmentEvaluationConflictError,
    AssessmentEvaluationNotFoundError,
    AssessmentEvaluationUnavailableError,
    AssessmentEvaluationValidationError,
    build_assessment_evaluation_service,
)
from personal_learning_assistant.services.assessment_intelligence_service import (
    AssessmentIntelligenceNotFoundError,
    AssessmentIntelligenceUnavailableError,
    build_assessment_intelligence_service,
)
from personal_learning_assistant.services.adaptive_academic_loop_service import (
    AdaptiveAcademicLoopConflictError,
    AdaptiveAcademicLoopNotFoundError,
    AdaptiveAcademicLoopUnavailableError,
    AdaptiveAcademicLoopValidationError,
    build_adaptive_academic_loop_service,
)
from personal_learning_assistant.services.calendar_grades_dashboard_service import (
    load_calendar_grades_dashboard,
    unavailable_calendar_grades_dashboard,
)
from personal_learning_assistant.services.course_dashboard_service import (
    load_course_catalogue,
    unavailable_course_catalogue,
)
from personal_learning_assistant.services.home_dashboard_service import (
    load_home_dashboard,
    unavailable_home_dashboard,
)
from personal_learning_assistant.services.knowledge_dashboard_service import (
    load_knowledge_dashboard,
    unavailable_knowledge_dashboard,
)
from personal_learning_assistant.services.knowledge_reader_service import (
    KnowledgeReaderNotFoundError,
    KnowledgeReaderUnavailableError,
    build_knowledge_reader_service,
)
from personal_learning_assistant.services.unified_search_runtime import (
    UnifiedSearchStaleIndexError,
)
from personal_learning_assistant.services.unified_search_service import (
    UnifiedSearchError,
    build_unified_search_service,
)
from personal_learning_assistant.services.notes_resources_dashboard_service import (
    load_notes_dashboard,
    load_resources_dashboard,
    unavailable_notes_dashboard,
    unavailable_resources_dashboard,
)
from personal_learning_assistant.services.notes_resources_web_service import (
    NotesResourcesWebNotFoundError,
    NotesResourcesWebUnavailableError,
    NotesResourcesWebValidationError,
    build_notes_resources_web_service,
)
from personal_learning_assistant.services.notes_studio_library_service import (
    build_notes_studio_library_web_service,
    unavailable_notes_studio_library,
)
from personal_learning_assistant.services.notes_studio_lifecycle_service import (
    NotesStudioLifecycleConflictError,
    NotesStudioLifecycleNotFoundError,
    NotesStudioLifecycleUnavailableError,
    NotesStudioLifecycleValidationError,
    build_notes_studio_lifecycle_service,
)
from personal_learning_assistant.services.notes_studio_reconciliation_service import (
    build_notes_studio_reconciliation_service,
)
from personal_learning_assistant.services.notes_studio_asset_service import (
    NotesStudioAssetNotFoundError,
    NotesStudioAssetUnavailableError,
    build_notes_studio_asset_service,
)
from personal_learning_assistant.services.notes_studio_editor_service import (
    NotesStudioEditorConflictError,
    NotesStudioEditorNotFoundError,
    NotesStudioEditorUnavailableError,
    NotesStudioEditorValidationError,
    build_notes_studio_editor_web_service,
)
from personal_learning_assistant.services.notes_studio_read_service import (
    NotesStudioReadNotFoundError,
    NotesStudioReadUnavailableError,
)
from personal_learning_assistant.services.notes_studio_reader_service import (
    build_notes_studio_reader_web_service,
)
from personal_learning_assistant.services.notes_studio_template_service import (
    NotesStudioTemplateNotFoundError,
    build_notes_studio_template_service,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceNotFoundError,
    ObsidianWorkspaceUnavailableError,
    ObsidianWorkspaceValidationError,
    build_obsidian_workspace_service,
    unavailable_obsidian_workspace,
)
from personal_learning_assistant.services.obsidian_study_companion_service import (
    ObsidianStudyConflictError,
    ObsidianStudyNotFoundError,
    ObsidianStudyUnavailableError,
    ObsidianStudyValidationError,
    build_obsidian_study_companion_service,
)
from personal_learning_assistant.services.planning_dashboard_service import (
    load_planning_dashboard,
    unavailable_planning_dashboard,
)
from personal_learning_assistant.services.operational_planner_web_service import (
    OperationalPlannerWebConflictError,
    OperationalPlannerWebNotFoundError,
    OperationalPlannerWebUnavailableError,
    OperationalPlannerWebValidationError,
    build_operational_planner_web_service,
)


web_blueprint = Blueprint("web", __name__)


def _home_dashboard():
    provider = current_app.config.get("HOME_DASHBOARD_PROVIDER") or load_home_dashboard
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Home academic brief unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_home_dashboard()


def _course_catalogue():
    provider = current_app.config.get("COURSE_CATALOGUE_PROVIDER") or load_course_catalogue
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Course catalogue unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_course_catalogue()


def _assessment_catalogue():
    provider = (
        current_app.config.get("ASSESSMENT_CATALOGUE_PROVIDER")
        or load_assessment_catalogue
    )
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Assessment catalogue unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_assessment_catalogue()


def _assessment_studio_service():
    factory = current_app.config.get("ASSESSMENT_STUDIO_SERVICE_FACTORY")
    return factory() if factory is not None else build_assessment_studio_service()


def _assessment_package_service():
    factory = current_app.config.get("ASSESSMENT_PACKAGE_SERVICE_FACTORY")
    return factory() if factory is not None else build_assessment_package_service()


def _assessment_runner_service():
    factory = current_app.config.get("ASSESSMENT_RUNNER_SERVICE_FACTORY")
    return factory() if factory is not None else build_assessment_runner_service()


def _assessment_evaluation_service():
    factory = current_app.config.get("ASSESSMENT_EVALUATION_SERVICE_FACTORY")
    return factory() if factory is not None else build_assessment_evaluation_service()


def _assessment_intelligence_service():
    factory = current_app.config.get("ASSESSMENT_INTELLIGENCE_SERVICE_FACTORY")
    return factory() if factory is not None else build_assessment_intelligence_service()


def _adaptive_academic_loop_service():
    factory = current_app.config.get("ADAPTIVE_ACADEMIC_LOOP_SERVICE_FACTORY")
    return factory() if factory is not None else build_adaptive_academic_loop_service()


def _adaptive_academic_loop_error_status(error):
    if isinstance(error, AdaptiveAcademicLoopValidationError):
        return 400
    if isinstance(error, AdaptiveAcademicLoopNotFoundError):
        return 404
    if isinstance(error, AdaptiveAcademicLoopConflictError):
        return 409
    return 503


def _assessment_intelligence_error_status(error):
    if isinstance(error, AssessmentIntelligenceNotFoundError):
        return 404
    return 503


def _assessment_evaluation_error_status(error):
    if isinstance(error, AssessmentEvaluationValidationError):
        return 400
    if isinstance(error, AssessmentEvaluationNotFoundError):
        return 404
    if isinstance(error, AssessmentEvaluationConflictError):
        return 409
    return 503


def _assessment_runner_error_status(error):
    if isinstance(error, AssessmentRunnerValidationError):
        return 400
    if isinstance(error, AssessmentRunnerNotFoundError):
        return 404
    if isinstance(error, AssessmentRunnerConflictError):
        return 409
    return 503


def _assessment_package_error_status(error):
    if isinstance(error, AssessmentPackageValidationError):
        return 400
    if isinstance(error, AssessmentPackageNotFoundError):
        return 404
    if isinstance(error, AssessmentPackageConflictError):
        return 409
    return 503


def _unavailable_assessment_studio():
    return {
        "available": False,
        "message": (
            "Assessment templates are unavailable until the canonical SQLite "
            "database has migration 0009. Existing assessment data was not changed."
        ),
        "courses": (),
        "templates": (),
        "active_template_count": 0,
        "presets": (),
    }


def _safe_assessment_studio():
    try:
        return _assessment_studio_service().overview()
    except Exception as error:
        current_app.logger.warning(
            "Assessment Studio unavailable (%s).", type(error).__name__
        )
        return _unavailable_assessment_studio()


def _assessment_template_payload():
    return {
        "course_id": request.form.get("course_id", ""),
        "name": request.form.get("name", ""),
        "assessment_type": request.form.get("assessment_type", ""),
        "mode": request.form.get("mode", ""),
        "description": request.form.get("description", ""),
        "instructions": request.form.get("instructions", ""),
        "duration_minutes": request.form.get("duration_minutes", ""),
        "total_marks": request.form.get("total_marks", ""),
        "revision": request.form.get("revision", ""),
        "topic_ids": request.form.getlist("topic_ids"),
        "pattern_types": request.form.getlist("pattern_type"),
        "pattern_counts": request.form.getlist("pattern_count"),
        "pattern_marks": request.form.getlist("pattern_marks"),
        "pattern_negative_marks": request.form.getlist("pattern_negative_marks"),
        "pattern_scoring_policies": request.form.getlist("pattern_scoring_policy"),
    }


def _assessment_studio_error_status(error):
    if isinstance(error, AssessmentStudioValidationError):
        return 400
    if isinstance(error, AssessmentStudioNotFoundError):
        return 404
    if isinstance(error, AssessmentStudioConflictError):
        return 409
    return 503


def _planning_dashboard():
    provider = (
        current_app.config.get("PLANNING_DASHBOARD_PROVIDER")
        or load_planning_dashboard
    )
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Progress and planning unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_planning_dashboard()


def _calendar_grades_dashboard():
    provider = (
        current_app.config.get("CALENDAR_GRADES_PROVIDER")
        or load_calendar_grades_dashboard
    )
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Calendar and grades unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_calendar_grades_dashboard()


def _notes_dashboard():
    provider = current_app.config.get("NOTES_DASHBOARD_PROVIDER") or load_notes_dashboard
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Notes unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_notes_dashboard()


def _resources_dashboard():
    provider = (
        current_app.config.get("RESOURCES_DASHBOARD_PROVIDER")
        or load_resources_dashboard
    )
    try:
        return provider()
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Resources unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_resources_dashboard()


def _knowledge_dashboard(query):
    provider = (
        current_app.config.get("KNOWLEDGE_DASHBOARD_PROVIDER")
        or load_knowledge_dashboard
    )
    try:
        return provider(query)
    except Exception as error:  # The web boundary must degrade safely on read failure.
        current_app.logger.warning(
            "Knowledge base unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_knowledge_dashboard(query)


def _unified_search_service():
    factory = current_app.config.get("UNIFIED_SEARCH_SERVICE_FACTORY")
    return factory() if factory is not None else build_unified_search_service()


def _knowledge_reader_service():
    factory = current_app.config.get("KNOWLEDGE_READER_SERVICE_FACTORY")
    return factory() if factory is not None else build_knowledge_reader_service()


def _academic_agent_service():
    factory = (
        current_app.config.get("ACADEMIC_AGENT_WEB_SERVICE_FACTORY")
        or build_academic_agent_web_service
    )
    return factory()


def _anvaya_notes_service():
    factory = current_app.config.get("ANVAYA_NOTES_SERVICE_FACTORY")
    return factory() if factory is not None else build_anvaya_notes_service()


def _notes_resources_service():
    factory = (
        current_app.config.get("NOTES_RESOURCES_WEB_SERVICE_FACTORY")
        or build_notes_resources_web_service
    )
    return factory()


def _notes_studio_library_service():
    factory = current_app.config.get("NOTES_STUDIO_LIBRARY_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_library_web_service()


def _notes_studio_lifecycle_service():
    factory = current_app.config.get("NOTES_STUDIO_LIFECYCLE_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_lifecycle_service()


def _notes_studio_reconciliation_service():
    factory = current_app.config.get("NOTES_STUDIO_RECONCILIATION_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_reconciliation_service()


def _notes_studio_asset_service():
    factory = current_app.config.get("NOTES_STUDIO_ASSET_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_asset_service()


def _notes_studio_editor_service():
    factory = current_app.config.get("NOTES_STUDIO_EDITOR_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_editor_web_service()


def _notes_studio_reader_service():
    factory = current_app.config.get("NOTES_STUDIO_READER_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_reader_web_service()


def _notes_studio_template_service():
    factory = current_app.config.get("NOTES_STUDIO_TEMPLATE_SERVICE_FACTORY")
    return factory() if factory is not None else build_notes_studio_template_service()


def _compat_factory_configured(name):
    """Old Phase 7.5.15 Notes/Obsidian bridges run only when explicitly injected."""
    return current_app.config.get(name) is not None


def _legacy_notes_get_override_configured():
    """Preserve explicit Phase 7.5.11 test/host overrides without affecting production."""
    return (
        current_app.config.get("NOTES_STUDIO_LIBRARY_SERVICE_FACTORY") is None
        and (
            current_app.config.get("NOTES_DASHBOARD_PROVIDER") is not None
            or current_app.config.get("NOTES_RESOURCES_WEB_SERVICE_FACTORY") is not None
        )
    )


def _obsidian_workspace_service():
    factory = (
        current_app.config.get("OBSIDIAN_WORKSPACE_SERVICE_FACTORY")
        or build_obsidian_workspace_service
    )
    return factory()


def _obsidian_study_service():
    factory = current_app.config.get("OBSIDIAN_STUDY_SERVICE_FACTORY")
    if factory is not None:
        return factory()
    return build_obsidian_study_companion_service(
        workspace_service=_obsidian_workspace_service()
    )


def _operational_planner_service():
    factory = current_app.config.get("OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY")
    if factory is not None:
        return factory()
    return build_operational_planner_web_service()


def _unavailable_operational_home():
    return {
        "available": False,
        "today": "",
        "task_summary": {"open": 0, "p0": 0, "p1": 0, "p2": 0},
        "agenda": None,
        "today_preview": {
            "summary": {
                "scheduled_focus_minutes": 0,
                "fixed_count": 0,
                "task_count": 0,
                "p0": 0,
            }
        },
        "daily_review_status": "unavailable",
    }


def _safe_operational_home():
    try:
        return _operational_planner_service().planning_home()
    except Exception as error:
        current_app.logger.warning(
            "Operational planner unavailable (%s).", type(error).__name__
        )
        return _unavailable_operational_home()


def _unavailable_operational_calendar(view="month", anchor_date=""):
    return {
        "available": False,
        "view": view,
        "anchor_date": anchor_date,
        "starts_on": "",
        "ends_on": "",
        "items": (),
        "days": {},
        "waiting_exam_slots": (),
    }


def _safe_operational_calendar(view, anchor_date):
    try:
        return _operational_planner_service().calendar_view(
            view=view,
            anchor_date=anchor_date or None,
        )
    except Exception as error:
        current_app.logger.warning(
            "Operational calendar unavailable (%s).", type(error).__name__
        )
        return _unavailable_operational_calendar(view, anchor_date)


def _planner_error_status(error):
    if isinstance(error, OperationalPlannerWebValidationError):
        return 400
    if isinstance(error, OperationalPlannerWebNotFoundError):
        return 404
    if isinstance(error, OperationalPlannerWebConflictError):
        return 409
    return 503


def _render_obsidian_note_error(message, status):
    return (
        render_template(
            "obsidian_note.html",
            active_page="obsidian",
            note=None,
            error_message=message,
        ),
        status,
    )


def _study_error_status(error):
    if isinstance(
        error,
        (ObsidianWorkspaceValidationError, ObsidianStudyValidationError),
    ):
        return 400, "invalid_request"
    if isinstance(
        error,
        (ObsidianWorkspaceNotFoundError, ObsidianStudyNotFoundError),
    ):
        return 404, "not_found"
    if isinstance(error, ObsidianStudyConflictError):
        return 409, "conflict"
    return 503, "unavailable"


def _tracking_error(error):
    status, code = _study_error_status(error)
    current_app.logger.warning(
        "Obsidian reading command rejected (%s).",
        type(error).__name__,
    )
    return jsonify(ok=False, error=code), status


def _tracking_payload(required):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or any(key not in payload for key in required):
        raise ObsidianStudyValidationError("The tracking request is incomplete.")
    return payload


def _companion_redirect(relative_path, result, tab):
    return redirect(
        url_for(
            "web.obsidian_note",
            path=relative_path,
            companion_saved=result,
            study_tools="1",
            study_tab=tab,
        ),
        code=303,
    )


def _companion_error(error):
    status, _code = _study_error_status(error)
    messages = {
        400: "The Companion entry is invalid or too long.",
        404: "That note or Companion entry was not found.",
        409: "The note changed. Refresh the Reader and try again.",
        503: "Study history and Companion are temporarily unavailable.",
    }
    current_app.logger.warning(
        "Obsidian Companion command rejected (%s).",
        type(error).__name__,
    )
    return _render_obsidian_note_error(messages[status], status)


def _safe_obsidian_workspace(service, query=""):
    try:
        return service.workspace(query)
    except Exception as error:
        current_app.logger.warning(
            "Obsidian workspace unavailable (%s).",
            type(error).__name__,
        )
        return unavailable_obsidian_workspace()


def _render_obsidian_command_error(service, message, status):
    return (
        render_template(
            "obsidian.html",
            active_page="obsidian",
            dashboard=_safe_obsidian_workspace(service),
            error_message=message,
            notice_message="",
        ),
        status,
    )


def _legacy_notes_workspace_if_configured(query):
    provider = current_app.config.get("NOTES_DASHBOARD_PROVIDER")
    if provider is None:
        return None
    workspace = _notes_dashboard()
    workspace["query"] = dict(query)
    return workspace


def _legacy_resources_workspace_if_configured(query):
    provider = current_app.config.get("RESOURCES_DASHBOARD_PROVIDER")
    if provider is None:
        return None
    workspace = _resources_dashboard()
    workspace["query"] = dict(query)
    return workspace


def _notes_workspace(service, query):
    legacy = _legacy_notes_workspace_if_configured(query)
    if legacy is not None:
        return legacy
    return service.notes_workspace(
        search=query["search"],
        topic=query["topic"],
        difficulty=query["difficulty"],
    )


def _resources_workspace(service, query):
    legacy = _legacy_resources_workspace_if_configured(query)
    if legacy is not None:
        return legacy
    return service.resources_workspace(
        search=query["search"],
        resource_type=query["type"],
        status=query["status"],
    )


def _safe_notes_workspace(service, query):
    try:
        return _notes_workspace(service, query)
    except Exception as error:
        current_app.logger.warning("Notes unavailable (%s).", type(error).__name__)
        workspace = unavailable_notes_dashboard()
        workspace["query"] = dict(query)
        return workspace


def _safe_resources_workspace(service, query):
    try:
        return _resources_workspace(service, query)
    except Exception as error:
        current_app.logger.warning("Resources unavailable (%s).", type(error).__name__)
        workspace = unavailable_resources_dashboard()
        workspace["query"] = dict(query)
        return workspace


def _render_notes_command_error(service, message, status):
    query = {"search": "", "topic": "", "difficulty": ""}
    return (
        render_template(
            "notes.html",
            active_page="notes",
            dashboard=_safe_notes_workspace(service, query),
            error_message=message,
        ),
        status,
    )


def _render_resources_command_error(service, message, status):
    query = {"search": "", "type": "", "status": ""}
    return (
        render_template(
            "resources.html",
            active_page="resources",
            dashboard=_safe_resources_workspace(service, query),
            error_message=message,
        ),
        status,
    )


def _unavailable_agent_workspace(message="Academic Agent is temporarily unavailable."):
    return {
        "available": False,
        "message": message,
        "provider_configured": False,
        "courses": [],
        "selected_course_code": "",
        "mentor": None,
        "sessions": [],
        "modes": [],
        "source_policies": [],
    }


def _render_session_error(service, session_id, message, status):
    session = None
    if status != 404:
        try:
            session = service.session_view(session_id)
        except Exception:
            session = None
    return (
        render_template(
            "agent_session.html",
            active_page="agent",
            session=session,
            error_message=message,
        ),
        status,
    )


@web_blueprint.get("/")
def home():
    """Render Home with the academic brief plus a read-only operational Today summary."""
    return render_template(
        "home.html",
        active_page="home",
        dashboard=_home_dashboard(),
        operational_today=_safe_operational_home(),
    )


@web_blueprint.get("/analysis")
def analysis():
    """Render the dedicated, read-only academic + Notes analysis hub."""
    academic = _home_dashboard()
    try:
        notes = _anvaya_notes_service().analysis()
    except AnvayaNotesUnavailableError:
        notes = {
            "available": False,
            "summary": {
                "total": 0,
                "typed": 0,
                "handwritten": 0,
                "saved_notes": 0,
                "doubts": 0,
                "media": 0,
                "inline_media": 0,
            },
            "type_percent": {"typed": 0, "handwritten": 0},
            "courses": [],
        }

    risks = list(academic.get("risks", []))
    priorities = list(academic.get("priorities", []))
    risk_max = max([float(item.get("score") or 0) for item in risks] or [1.0])
    priority_max = max([float(item.get("score") or 0) for item in priorities] or [1.0])

    study_totals = {}
    if "study_minutes_by_course" in academic:
        study_totals = dict(academic["study_minutes_by_course"])
    else:
        for item in academic.get("study_blocks", []):
            code = str(item.get("course_code") or "COURSE")
            study_totals[code] = study_totals.get(code, 0) + int(item.get("minutes") or 0)
    study_max = max(list(study_totals.values()) or [1])

    view = {
        "academic": academic,
        "notes": notes,
        "risk_rows": [
            {**item, "percent": round((float(item.get("score") or 0) / risk_max) * 100, 1)}
            for item in risks
        ],
        "priority_rows": [
            {**item, "percent": round((float(item.get("score") or 0) / priority_max) * 100, 1)}
            for item in priorities
        ],
        "study_rows": [
            {
                "course_code": code,
                "minutes": minutes,
                "percent": round((minutes / study_max) * 100, 1),
            }
            for code, minutes in sorted(
                study_totals.items(),
                key=lambda pair: (-pair[1], pair[0]),
            )
        ],
    }
    return render_template("analysis.html", active_page="analysis", analysis=view)


@web_blueprint.get("/courses")
def courses():
    """Render the read-only Courses & Topics catalogue."""
    return render_template("courses.html", active_page="courses", catalogue=_course_catalogue())


@web_blueprint.get("/assessments")
def assessments():
    """Render Assessment Studio without mutating academic state."""
    return render_template("assessments.html",
        active_page="assessments",
        catalogue=_assessment_catalogue(),
        studio=_safe_assessment_studio(),
    )


@web_blueprint.get("/assessments/courses/<course_id>")
def assessment_course(course_id):
    try:
        workspace = _assessment_studio_service().course_workspace(course_id)
        return render_template(
            "assessment_course.html",
            active_page="assessments",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:
        return (
            render_template(
                "assessment_course.html",
                active_page="assessments",
                workspace=None,
                error_message=str(error),
            ),
            _assessment_studio_error_status(error),
        )


@web_blueprint.get("/assessments/templates")
def assessment_templates():
    try:
        view = _assessment_studio_service().list_templates(
            course_id=request.args.get("course_id", "", type=str).strip() or None
        )
        return render_template(
            "assessment_templates.html",
            active_page="assessments",
            view=view,
            error_message="",
        )
    except Exception as error:
        return (
            render_template(
                "assessment_templates.html",
                active_page="assessments",
                view={"templates": (), "courses": (), "selected_course_id": ""},
                error_message=str(error),
            ),
            _assessment_studio_error_status(error),
        )


@web_blueprint.get("/assessments/templates/new")
def assessment_template_new():
    try:
        context = _assessment_studio_service().form_context(
            course_id=request.args.get("course_id", "", type=str).strip(),
            preset=request.args.get("preset", "", type=str).strip(),
        )
        return render_template(
            "assessment_template_form.html",
            active_page="assessments",
            context=context,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.post("/assessments/templates")
def assessment_template_create():
    service = _assessment_studio_service()
    payload = _assessment_template_payload()
    try:
        item = service.create_template(payload)
        return redirect(
            url_for("web.assessment_template_detail", template_id=item["id"]),
            code=303,
        )
    except (AssessmentStudioValidationError, AssessmentStudioConflictError) as error:
        try:
            context = service.form_context(draft=payload)
        except Exception:
            return str(error), _assessment_studio_error_status(error)
        return (
            render_template(
                "assessment_template_form.html",
                active_page="assessments",
                context=context,
                error_message=str(error),
            ),
            _assessment_studio_error_status(error),
        )
    except AssessmentStudioUnavailableError as error:
        return str(error), 503


@web_blueprint.get("/assessments/templates/<template_id>")
def assessment_template_detail(template_id):
    try:
        item = _assessment_studio_service().template_detail(template_id)
        return render_template(
            "assessment_template_detail.html",
            active_page="assessments",
            item=item,
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.get("/assessments/templates/<template_id>/edit")
def assessment_template_edit(template_id):
    try:
        context = _assessment_studio_service().form_context(template_id=template_id)
        return render_template(
            "assessment_template_form.html",
            active_page="assessments",
            context=context,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.post("/assessments/templates/<template_id>")
def assessment_template_update(template_id):
    service = _assessment_studio_service()
    payload = _assessment_template_payload()
    try:
        item = service.update_template(template_id, payload)
        return redirect(
            url_for("web.assessment_template_detail", template_id=item["id"]),
            code=303,
        )
    except (AssessmentStudioValidationError, AssessmentStudioConflictError) as error:
        try:
            context = service.form_context(template_id=template_id, draft=payload)
        except Exception:
            return str(error), _assessment_studio_error_status(error)
        return (
            render_template(
                "assessment_template_form.html",
                active_page="assessments",
                context=context,
                error_message=str(error),
            ),
            _assessment_studio_error_status(error),
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.post("/assessments/templates/<template_id>/deactivate")
def assessment_template_deactivate(template_id):
    try:
        item = _assessment_studio_service().set_active(
            template_id,
            revision=request.form.get("revision", ""),
            active=False,
        )
        return redirect(
            url_for("web.assessment_template_detail", template_id=item["id"]),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.post("/assessments/templates/<template_id>/reactivate")
def assessment_template_reactivate(template_id):
    try:
        item = _assessment_studio_service().set_active(
            template_id,
            revision=request.form.get("revision", ""),
            active=True,
        )
        return redirect(
            url_for("web.assessment_template_detail", template_id=item["id"]),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_studio_error_status(error)


@web_blueprint.get("/assessments/import")
def assessment_import():
    """List staged packages and render the explicit package upload form."""
    try:
        workspace = _assessment_package_service().workspace()
        return render_template(
            "assessment_import.html",
            active_page="assessments",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:
        return (
            render_template(
                "assessment_import.html",
                active_page="assessments",
                workspace={
                    "available": False,
                    "batches": (),
                    "schema": "anvaya.assessment-package",
                    "version": 1,
                },
                error_message=str(error),
            ),
            _assessment_package_error_status(error),
        )


@web_blueprint.post("/assessments/import")
def assessment_import_create():
    """Validate and stage one external ANVAYA Assessment Package."""
    service = _assessment_package_service()
    upload = request.files.get("package")
    try:
        if upload is None or not upload.filename:
            raise AssessmentPackageValidationError(
                "Choose an ANVAYA Assessment Package JSON file."
            )
        item = service.stage_upload(
            upload.filename,
            upload.read(MAX_PACKAGE_BYTES + 1),
        )
        return redirect(
            url_for("web.assessment_import_review", batch_id=item["id"], staged="1"),
            code=303,
        )
    except Exception as error:
        try:
            workspace = service.workspace()
        except Exception:
            workspace = {
                "available": False,
                "batches": (),
                "schema": "anvaya.assessment-package",
                "version": 1,
            }
        return (
            render_template(
                "assessment_import.html",
                active_page="assessments",
                workspace=workspace,
                error_message=str(error),
            ),
            _assessment_package_error_status(error),
        )


@web_blueprint.get("/assessments/import/<batch_id>/review")
def assessment_import_review(batch_id):
    try:
        batch = _assessment_package_service().review(batch_id)
        notice = ""
        if request.args.get("staged") == "1":
            notice = "Package validated and staged. Review it before approval."
        elif request.args.get("saved") == "1":
            notice = "Review changes saved."
        elif request.args.get("approved") == "1":
            notice = "Package approved and committed as a canonical assessment."
        elif request.args.get("rejected") == "1":
            notice = "Package rejected. No canonical assessment was created."
        return render_template(
            "assessment_import_review.html",
            active_page="assessments",
            batch=batch,
            error_message="",
            notice_message=notice,
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/metadata")
def assessment_import_metadata(batch_id):
    service = _assessment_package_service()
    try:
        service.update_metadata(
            batch_id,
            {
                "title": request.form.get("title", ""),
                "assessment_type": request.form.get("assessment_type", ""),
                "mode": request.form.get("mode", ""),
                "duration_minutes": request.form.get("duration_minutes", ""),
                "total_marks": request.form.get("total_marks", ""),
                "instructions_text": request.form.get("instructions_text", ""),
            },
        )
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        try:
            batch = service.review(batch_id)
            return (
                render_template(
                    "assessment_import_review.html",
                    active_page="assessments",
                    batch=batch,
                    error_message=str(error),
                    notice_message="",
                ),
                _assessment_package_error_status(error),
            )
        except Exception:
            return str(error), _assessment_package_error_status(error)


@web_blueprint.get("/assessments/import/<batch_id>/questions/<question_id>/edit")
def assessment_import_question_edit(batch_id, question_id):
    try:
        editor = _assessment_package_service().question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        return render_template(
            "assessment_import_question_edit.html",
            active_page="assessments",
            editor=editor,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/questions/<question_id>/edit")
def assessment_import_question_update(batch_id, question_id):
    service = _assessment_package_service()
    payload = {
        "question_number": request.form.get("question_number", ""),
        "section_label": request.form.get("section_label", ""),
        "question_type": request.form.get("question_type", ""),
        "question_text": request.form.get("question_text", ""),
        "marks": request.form.get("marks", ""),
        "negative_marks": request.form.get("negative_marks", ""),
        "scoring_policy": request.form.get("scoring_policy", ""),
        "difficulty": request.form.get("difficulty", ""),
        "estimated_minutes": request.form.get("estimated_minutes", ""),
        "selected_topic_id": request.form.get("selected_topic_id", ""),
        "chapter_label": request.form.get("chapter_label", ""),
        "raw_topic_label": request.form.get("raw_topic_label", ""),
        "subtopic_label": request.form.get("subtopic_label", ""),
        "concepts": request.form.get("concepts", ""),
        "expected_method": request.form.get("expected_method", ""),
        "solution_text": request.form.get("solution_text", ""),
        "rubric_text": request.form.get("rubric_text", ""),
        "source_kind": request.form.get("source_kind", ""),
        "source_label": request.form.get("source_label", ""),
        "source_page": request.form.get("source_page", ""),
        "source_locator": request.form.get("source_locator", ""),
        "accepted_answers": request.form.get("accepted_answers", ""),
        "correct_option_ids": request.form.getlist("correct_option_ids"),
        "option_texts": request.form.getlist("option_text"),
        "review_complete": request.form.get("review_complete") == "1",
    }
    try:
        editor = service.question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        service.update_question(question_id, payload)
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        try:
            editor = service.question_editor(question_id)
            return (
                render_template(
                    "assessment_import_question_edit.html",
                    active_page="assessments",
                    editor=editor,
                    error_message=str(error),
                ),
                _assessment_package_error_status(error),
            )
        except Exception:
            return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/questions/<question_id>/reorder")
def assessment_import_question_reorder(batch_id, question_id):
    try:
        editor = _assessment_package_service().question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        _assessment_package_service().reorder(
            question_id, request.form.get("direction", "")
        )
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.get("/assessments/import/<batch_id>/questions/<question_id>/split")
def assessment_import_question_split(batch_id, question_id):
    try:
        editor = _assessment_package_service().question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        return render_template(
            "assessment_import_split.html",
            active_page="assessments",
            editor=editor,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/questions/<question_id>/split")
def assessment_import_question_split_create(batch_id, question_id):
    service = _assessment_package_service()
    try:
        editor = service.question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        service.split(question_id, request.form.get("marker", ""))
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        try:
            editor = service.question_editor(question_id)
            return (
                render_template(
                    "assessment_import_split.html",
                    active_page="assessments",
                    editor=editor,
                    error_message=str(error),
                ),
                _assessment_package_error_status(error),
            )
        except Exception:
            return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/questions/<question_id>/merge-next")
def assessment_import_question_merge(batch_id, question_id):
    try:
        editor = _assessment_package_service().question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        _assessment_package_service().merge_next(question_id)
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/questions/<question_id>/remove")
def assessment_import_question_remove(batch_id, question_id):
    try:
        editor = _assessment_package_service().question_editor(question_id)
        if str(editor["batch"]["id"]) != str(batch_id):
            raise AssessmentPackageNotFoundError("Question does not belong to this import.")
        _assessment_package_service().remove(question_id)
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, saved="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/approve")
def assessment_import_approve(batch_id):
    service = _assessment_package_service()
    try:
        service.approve(batch_id)
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, approved="1"),
            code=303,
        )
    except Exception as error:
        try:
            batch = service.review(batch_id)
            return (
                render_template(
                    "assessment_import_review.html",
                    active_page="assessments",
                    batch=batch,
                    error_message=str(error),
                    notice_message="",
                ),
                _assessment_package_error_status(error),
            )
        except Exception:
            return str(error), _assessment_package_error_status(error)


@web_blueprint.post("/assessments/import/<batch_id>/reject")
def assessment_import_reject(batch_id):
    try:
        _assessment_package_service().reject(batch_id)
        return redirect(
            url_for("web.assessment_import_review", batch_id=batch_id, rejected="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_package_error_status(error)


@web_blueprint.get("/assessments/tests")
def assessment_tests():
    """List runnable approved assessments and persisted timed sessions."""
    try:
        workspace = _assessment_runner_service().library()
        return render_template(
            "assessment_test_library.html",
            active_page="assessments",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:
        return (
            render_template(
                "assessment_test_library.html",
                active_page="assessments",
                workspace={"available": False, "assessments": (), "sessions": ()},
                error_message=str(error),
            ),
            _assessment_runner_error_status(error),
        )


@web_blueprint.get("/assessments/tests/<assessment_id>")
def assessment_test_preflight(assessment_id):
    try:
        test = _assessment_runner_service().preflight(assessment_id)
        return render_template(
            "assessment_test_preflight.html",
            active_page="assessments",
            test=test,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_runner_error_status(error)


@web_blueprint.post("/assessments/tests/<assessment_id>/start")
def assessment_test_start(assessment_id):
    try:
        result = _assessment_runner_service().start(
            assessment_id,
            confirmed=request.form.get("confirmed") == "1",
        )
        return redirect(
            url_for("web.assessment_session", session_id=result["session_id"]),
            code=303,
        )
    except Exception as error:
        try:
            test = _assessment_runner_service().preflight(assessment_id)
            return (
                render_template(
                    "assessment_test_preflight.html",
                    active_page="assessments",
                    test=test,
                    error_message=str(error),
                ),
                _assessment_runner_error_status(error),
            )
        except Exception:
            return str(error), _assessment_runner_error_status(error)


@web_blueprint.get("/assessments/sessions/<session_id>")
def assessment_session(session_id):
    try:
        ordinal = request.args.get("q", default=None, type=int)
        view = _assessment_runner_service().runner_view(
            session_id,
            ordinal=ordinal,
        )
        if view.get("terminal"):
            return redirect(
                url_for("web.assessment_session_summary", session_id=session_id),
                code=303,
            )
        return render_template(
            "assessment_test_runner.html",
            active_page="assessments",
            view=view,
        )
    except Exception as error:
        return str(error), _assessment_runner_error_status(error)


@web_blueprint.post("/assessments/sessions/<session_id>/questions/<session_question_id>/autosave")
def assessment_session_autosave(session_id, session_question_id):
    service = _assessment_runner_service()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, error="invalid_request"), 400
    response = payload.get("response")
    if not isinstance(response, dict):
        return jsonify(ok=False, error="invalid_response"), 400
    try:
        result = service.save_response(
            session_id,
            session_question_id,
            response,
            mark_for_review=None,
            focus_seconds_delta=payload.get("focus_seconds_delta", 0),
            event_type="response_autosaved",
        )
        return jsonify(ok=True, **result)
    except Exception as error:
        return (
            jsonify(ok=False, error=str(error)),
            _assessment_runner_error_status(error),
        )


@web_blueprint.post("/assessments/sessions/<session_id>/heartbeat")
def assessment_session_heartbeat(session_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    try:
        result = _assessment_runner_service().heartbeat(
            session_id,
            session_question_id=payload.get("session_question_id"),
            focus_seconds_delta=payload.get("focus_seconds_delta", 0),
        )
        return jsonify(ok=True, **result)
    except Exception as error:
        return (
            jsonify(ok=False, error=str(error)),
            _assessment_runner_error_status(error),
        )


@web_blueprint.post("/assessments/sessions/<session_id>/questions/<session_question_id>/action")
def assessment_session_question_action(session_id, session_question_id):
    service = _assessment_runner_service()
    action = str(request.form.get("action") or "").strip()
    response = {
        "selected_option_ids": request.form.getlist("option_ids"),
        "value": request.form.get("answer_value", ""),
        "text": request.form.get("answer_text", ""),
    }
    current_ordinal = request.form.get("current_ordinal", type=int) or 1
    next_ordinal = request.form.get("next_ordinal", type=int) or current_ordinal
    focus = request.form.get("focus_seconds_delta", 0)

    try:
        if action == "clear":
            service.clear_response(
                session_id,
                session_question_id,
                focus_seconds_delta=focus,
            )
            target = current_ordinal
        elif action == "mark_next":
            service.save_response(
                session_id,
                session_question_id,
                response,
                mark_for_review=True,
                focus_seconds_delta=focus,
                event_type="marked_for_review",
            )
            target = next_ordinal
        elif action == "save_next":
            service.save_response(
                session_id,
                session_question_id,
                response,
                mark_for_review=False,
                focus_seconds_delta=focus,
                event_type="response_saved",
            )
            target = next_ordinal
        else:
            raise AssessmentRunnerValidationError("Unknown test action.")
        return redirect(
            url_for("web.assessment_session", session_id=session_id, q=target),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_runner_error_status(error)


@web_blueprint.post("/assessments/sessions/<session_id>/submit")
def assessment_session_submit(session_id):
    try:
        result = _assessment_runner_service().submit(session_id)
        if request.is_json or "application/json" in request.headers.get("Accept", ""):
            return jsonify(ok=True, **result)
        return redirect(
            url_for("web.assessment_session_summary", session_id=session_id),
            code=303,
        )
    except Exception as error:
        if request.is_json or "application/json" in request.headers.get("Accept", ""):
            return (
                jsonify(ok=False, error=str(error)),
                _assessment_runner_error_status(error),
            )
        return str(error), _assessment_runner_error_status(error)


@web_blueprint.get("/assessments/sessions/<session_id>/summary")
def assessment_session_summary(session_id):
    try:
        summary = _assessment_runner_service().summary(session_id)
        return render_template(
            "assessment_test_summary.html",
            active_page="assessments",
            summary=summary,
        )
    except Exception as error:
        return str(error), _assessment_runner_error_status(error)


@web_blueprint.post("/assessments/sessions/<session_id>/evaluate")
def assessment_session_evaluate(session_id):
    try:
        _assessment_evaluation_service().create(session_id)
        return redirect(
            url_for("web.assessment_evaluation_results", session_id=session_id, created="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.get("/assessments/sessions/<session_id>/evaluation")
def assessment_evaluation_results(session_id):
    try:
        result = _assessment_evaluation_service().results(session_id)
        notice = ""
        if request.args.get("created") == "1":
            notice = "Evaluation created. Deterministic questions were scored; subjective/custom questions remain under review."
        elif request.args.get("saved") == "1":
            notice = "Evaluation saved."
        elif request.args.get("confirmed") == "1":
            notice = "Provisional evaluation confirmed."
        elif request.args.get("mistake") == "1":
            notice = "Mistake classification recorded."
        elif request.args.get("mistake_confirmed") == "1":
            notice = "Provisional mistake classification confirmed."
        return render_template(
            "assessment_evaluation_results.html",
            active_page="assessments",
            result=result,
            mistake_categories=tuple(sorted(MISTAKE_CATEGORIES)),
            notice_message=notice,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.get("/assessments/evaluations/<evaluation_id>/review")
def assessment_evaluation_review(evaluation_id):
    try:
        item = _assessment_evaluation_service().response_editor(evaluation_id)
        return render_template(
            "assessment_evaluation_review.html",
            active_page="assessments",
            item=item,
            error_message="",
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.post("/assessments/evaluations/<evaluation_id>/review")
def assessment_evaluation_review_save(evaluation_id):
    service = _assessment_evaluation_service()
    payload = {
        "evaluator_type": request.form.get("evaluator_type", ""),
        "evaluator_model": request.form.get("evaluator_model", ""),
        "awarded_marks": request.form.get("awarded_marks", ""),
        "confidence": request.form.get("confidence", ""),
        "feedback_text": request.form.get("feedback_text", ""),
        "confirm_final": request.form.get("confirm_final") == "1",
    }
    try:
        service.save_manual_evaluation(evaluation_id, payload)
        item = service.response_editor(evaluation_id)
        return redirect(
            url_for("web.assessment_evaluation_results", session_id=item["session_id"], saved="1"),
            code=303,
        )
    except Exception as error:
        try:
            item = service.response_editor(evaluation_id)
            return (
                render_template(
                    "assessment_evaluation_review.html",
                    active_page="assessments",
                    item=item,
                    error_message=str(error),
                ),
                _assessment_evaluation_error_status(error),
            )
        except Exception:
            return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.post("/assessments/evaluations/<evaluation_id>/confirm")
def assessment_evaluation_confirm(evaluation_id):
    service = _assessment_evaluation_service()
    try:
        item = service.confirm_provisional(evaluation_id)
        return redirect(
            url_for("web.assessment_evaluation_results", session_id=item["session_id"], confirmed="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.post("/assessments/evaluations/<evaluation_id>/mistakes")
def assessment_evaluation_mistake_add(evaluation_id):
    service = _assessment_evaluation_service()
    try:
        item = service.classify_mistake(
            evaluation_id,
            {
                "category": request.form.get("category", ""),
                "note": request.form.get("note", ""),
                "source_type": request.form.get("source_type", "user"),
            },
        )
        return redirect(
            url_for("web.assessment_evaluation_results", session_id=item["session_id"], mistake="1"),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.post("/assessments/evaluation-mistakes/<mistake_id>/confirm")
def assessment_evaluation_mistake_confirm(mistake_id):
    service = _assessment_evaluation_service()
    try:
        item = service.confirm_mistake(mistake_id)
        return redirect(
            url_for(
                "web.assessment_evaluation_results",
                session_id=item["session_id"],
                mistake_confirmed="1",
            ),
            code=303,
        )
    except Exception as error:
        return str(error), _assessment_evaluation_error_status(error)


@web_blueprint.get("/assessments/reports")
def assessment_intelligence():
    try:
        report = _assessment_intelligence_service().overview()
        return render_template(
            "assessment_intelligence.html",
            active_page="assessments",
            report=report,
            error_message="",
        )
    except Exception as error:
        return (
            render_template(
                "assessment_intelligence.html",
                active_page="assessments",
                report={
                    "available": False,
                    "has_evidence": False,
                    "confirmed_session_count": 0,
                    "course_count": 0,
                    "courses": (),
                    "recent_trend": (),
                    "recovery_topics": (),
                    "mistake_patterns": (),
                    "historical": {
                        "session_count": 0,
                        "topics": (),
                        "note": "",
                    },
                },
                error_message=str(error),
            ),
            _assessment_intelligence_error_status(error),
        )


@web_blueprint.get("/assessments/reports/courses/<course_id>")
def assessment_intelligence_course(course_id):
    try:
        report = _assessment_intelligence_service().course_report(course_id)
        return render_template(
            "assessment_intelligence_course.html",
            active_page="assessments",
            report=report,
        )
    except Exception as error:
        return str(error), _assessment_intelligence_error_status(error)


@web_blueprint.get("/assessments/sessions/<session_id>/analysis")
def assessment_session_analysis(session_id):
    try:
        report = _assessment_intelligence_service().session_analysis(session_id)
        return render_template(
            "assessment_intelligence_session.html",
            active_page="assessments",
            report=report,
        )
    except Exception as error:
        return str(error), _assessment_intelligence_error_status(error)


@web_blueprint.get("/assessments/weak-topics")
def assessment_weak_topics():
    try:
        report = _assessment_intelligence_service().weak_topics()
        return render_template(
            "assessment_weak_topics.html",
            active_page="assessments",
            report=report,
        )
    except Exception as error:
        return str(error), _assessment_intelligence_error_status(error)


@web_blueprint.get("/assessments/adaptive")
def assessment_adaptive_loop():
    try:
        workspace = _adaptive_academic_loop_service().workspace()
        notice = ""
        if request.args.get("generated") == "1":
            notice = "Selected recovery recommendations were saved for review."
        elif request.args.get("applied") == "1":
            notice = "Recommendation applied to the planner backlog."
        elif request.args.get("rejected") == "1":
            notice = "Recommendation rejected. No planner task was created."
        return render_template(
            "assessment_adaptive_loop.html",
            active_page="assessments",
            workspace=workspace,
            notice_message=notice,
            error_message="",
        )
    except Exception as error:
        return str(error), _adaptive_academic_loop_error_status(error)


@web_blueprint.post("/assessments/adaptive/generate")
def assessment_adaptive_generate():
    service = _adaptive_academic_loop_service()
    try:
        service.generate(request.form.getlist("evidence_fingerprint"))
        return redirect(url_for("web.assessment_adaptive_loop", generated="1"), code=303)
    except (
        AdaptiveAcademicLoopValidationError,
        AdaptiveAcademicLoopNotFoundError,
        AdaptiveAcademicLoopConflictError,
        AdaptiveAcademicLoopUnavailableError,
    ) as error:
        try:
            workspace = service.workspace()
        except Exception:
            return str(error), _adaptive_academic_loop_error_status(error)
        return (
            render_template(
                "assessment_adaptive_loop.html",
                active_page="assessments",
                workspace=workspace,
                notice_message="",
                error_message=str(error),
            ),
            _adaptive_academic_loop_error_status(error),
        )


@web_blueprint.post("/assessments/adaptive/<recommendation_id>/apply")
def assessment_adaptive_apply(recommendation_id):
    service = _adaptive_academic_loop_service()
    try:
        service.apply(
            recommendation_id,
            {
                "revision": request.form.get("revision", ""),
                "title": request.form.get("title", ""),
                "description": request.form.get("description", ""),
                "priority": request.form.get("priority", ""),
                "estimated_minutes": request.form.get("estimated_minutes", ""),
                "due_on": request.form.get("due_on", ""),
            },
        )
        return redirect(url_for("web.assessment_adaptive_loop", applied="1"), code=303)
    except (
        AdaptiveAcademicLoopValidationError,
        AdaptiveAcademicLoopNotFoundError,
        AdaptiveAcademicLoopConflictError,
        AdaptiveAcademicLoopUnavailableError,
    ) as error:
        try:
            workspace = service.workspace()
        except Exception:
            return str(error), _adaptive_academic_loop_error_status(error)
        return (
            render_template(
                "assessment_adaptive_loop.html",
                active_page="assessments",
                workspace=workspace,
                notice_message="",
                error_message=str(error),
            ),
            _adaptive_academic_loop_error_status(error),
        )


@web_blueprint.post("/assessments/adaptive/<recommendation_id>/reject")
def assessment_adaptive_reject(recommendation_id):
    service = _adaptive_academic_loop_service()
    try:
        service.reject(
            recommendation_id,
            revision=request.form.get("revision", ""),
            reason=request.form.get("reason", ""),
        )
        return redirect(url_for("web.assessment_adaptive_loop", rejected="1"), code=303)
    except (
        AdaptiveAcademicLoopValidationError,
        AdaptiveAcademicLoopNotFoundError,
        AdaptiveAcademicLoopConflictError,
        AdaptiveAcademicLoopUnavailableError,
    ) as error:
        try:
            workspace = service.workspace()
        except Exception:
            return str(error), _adaptive_academic_loop_error_status(error)
        return (
            render_template(
                "assessment_adaptive_loop.html",
                active_page="assessments",
                workspace=workspace,
                notice_message="",
                error_message=str(error),
            ),
            _adaptive_academic_loop_error_status(error),
        )


@web_blueprint.get("/planning")
def planning():
    """Render the Operational Planner landing page plus existing progress evidence."""
    return render_template("planning.html", active_page="planning", dashboard=_planning_dashboard(), operational=_safe_operational_home())


@web_blueprint.get("/calendar")
def calendar():
    """Render Month/Week/Day operations while preserving the existing grade read model."""
    view = request.args.get("view", "month", type=str).strip().lower() or "month"
    anchor_date = request.args.get("date", "", type=str).strip()
    return render_template("calendar.html", active_page="calendar", dashboard=_calendar_grades_dashboard(), operational_calendar=_safe_operational_calendar(view, anchor_date))


@web_blueprint.get("/planning/tasks")
def planning_tasks():
    """Render operational tasks without creating or scheduling anything."""
    service = _operational_planner_service()
    try:
        workspace = service.tasks_workspace(
            status=request.args.get("status", "", type=str),
            priority=request.args.get("priority", "", type=str),
            course_id=request.args.get("course_id", "", type=str),
        )
        return render_template(
            "planning_tasks.html",
            active_page="planning",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:
        current_app.logger.warning("Operational tasks unavailable (%s).", type(error).__name__)
        return (
            render_template(
                "planning_tasks.html",
                active_page="planning",
                workspace={
                    "available": False,
                    "tasks": (),
                    "filters": {},
                    "summary": {"open": 0, "p0": 0, "p1": 0, "p2": 0},
                },
                error_message="Tasks are temporarily unavailable. Existing planner data was not changed.",
            ),
            503,
        )


@web_blueprint.post("/planning/tasks")
def planning_tasks_create():
    service = _operational_planner_service()
    try:
        service.create_task(
            title=request.form.get("title", ""),
            description=request.form.get("description", ""),
            priority=request.form.get("priority", "P1"),
            estimated_minutes=request.form.get("estimated_minutes", ""),
            due_on=request.form.get("due_on", ""),
            preferred_day=request.form.get("preferred_day", ""),
            preferred_window=request.form.get("preferred_window", ""),
            rollover_policy=request.form.get("rollover_policy", ""),
        )
        return redirect(url_for("web.planning_tasks", created="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        status = _planner_error_status(error)
        try:
            workspace = service.tasks_workspace()
        except Exception:
            workspace = {
                "available": False,
                "tasks": (),
                "filters": {},
                "summary": {"open": 0, "p0": 0, "p1": 0, "p2": 0},
            }
        return (
            render_template(
                "planning_tasks.html",
                active_page="planning",
                workspace=workspace,
                error_message=str(error),
            ),
            status,
        )


@web_blueprint.post("/planning/tasks/<task_id>")
def planning_task_update(task_id):
    """Edit one existing operational task through the planner service boundary."""
    try:
        _operational_planner_service().update_task(
            task_id,
            title=request.form.get("title", ""),
            description=request.form.get("description", ""),
            priority=request.form.get("priority", "P1"),
            estimated_minutes=request.form.get("estimated_minutes", ""),
            due_on=request.form.get("due_on", ""),
            preferred_day=request.form.get("preferred_day", ""),
            preferred_window=request.form.get("preferred_window", ""),
            rollover_policy=request.form.get("rollover_policy", ""),
        )
        return redirect(url_for("web.planning_tasks", updated="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/tasks/<task_id>/status")
def planning_task_transition(task_id):
    try:
        _operational_planner_service().transition_task(
            task_id, request.form.get("status", "")
        )
        return redirect(url_for("web.planning_tasks", updated="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.get("/planning/month-plan")
def planning_month_plan():
    return render_template(
        "planning_month_plan.html",
        active_page="planning",
        preview=None,
        error_message="",
        notice_message=(
            "Monthly plan imported successfully."
            if request.args.get("imported") == "1"
            else ""
        ),
    )


def _uploaded_month_plan():
    uploaded = request.files.get("plan_file")
    if uploaded is None or not uploaded.filename:
        raise OperationalPlannerWebValidationError("Choose a YAML month-plan file.")
    return uploaded.filename, uploaded.read()


@web_blueprint.post("/planning/month-plan/preview")
def planning_month_plan_preview():
    try:
        filename, payload = _uploaded_month_plan()
        preview = _operational_planner_service().preview_month_plan(filename, payload)
        return render_template(
            "planning_month_plan.html",
            active_page="planning",
            preview=preview,
            error_message="",
            notice_message="",
        )
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return (
            render_template(
                "planning_month_plan.html",
                active_page="planning",
                preview=None,
                error_message=str(error),
                notice_message="",
            ),
            _planner_error_status(error),
        )


@web_blueprint.post("/planning/month-plan/approve")
def planning_month_plan_approve():
    try:
        filename, payload = _uploaded_month_plan()
        _operational_planner_service().approve_month_plan(
            filename,
            payload,
            request.form.get("expected_sha256", ""),
        )
        return redirect(url_for("web.planning_month_plan", imported="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return (
            render_template(
                "planning_month_plan.html",
                active_page="planning",
                preview=None,
                error_message=str(error),
                notice_message="",
            ),
            _planner_error_status(error),
        )


@web_blueprint.get("/planning/day/<agenda_date>")
def planning_day(agenda_date):
    try:
        day = _operational_planner_service().day_view(agenda_date)
        return render_template(
            "planning_day.html",
            active_page="planning",
            day=day,
            error_message=request.args.get("error", "", type=str),
        )
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/day/<agenda_date>/generate")
def planning_day_generate(agenda_date):
    try:
        _operational_planner_service().generate_day(agenda_date)
        return redirect(url_for("web.planning_day", agenda_date=agenda_date), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/day/<agenda_date>/approve")
def planning_day_approve(agenda_date):
    try:
        _operational_planner_service().approve_day(agenda_date)
        return redirect(url_for("web.planning_day", agenda_date=agenda_date), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/day/<agenda_date>/items/<item_id>")
def planning_day_item_update(agenda_date, item_id):
    try:
        _operational_planner_service().update_day_item(
            agenda_date,
            item_id,
            status=request.form.get("status", ""),
            actual_minutes=request.form.get("actual_minutes", ""),
        )
        return redirect(url_for("web.planning_day", agenda_date=agenda_date), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/day/<agenda_date>/close")
def planning_day_close(agenda_date):
    try:
        _operational_planner_service().close_day(
            agenda_date,
            {
                "learned": request.form.get("learned", ""),
                "biggest_confusion": request.form.get("biggest_confusion", ""),
                "coding_completed": request.form.get("coding_completed") == "1",
                "coding_independent": request.form.get("coding_independent") == "1",
                "data_science_ai_assistance_level": request.form.get(
                    "data_science_ai_assistance_level", ""
                ),
                "energy_1_to_5": request.form.get("energy_1_to_5", ""),
                "sleep_target": request.form.get("sleep_target", ""),
                "tomorrow_first_task": request.form.get("tomorrow_first_task", ""),
            },
        )
        return redirect(url_for("web.planning_day", agenda_date=agenda_date), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.get("/planning/review/week/<anchor_date>")
def planning_weekly_review(anchor_date):
    try:
        workspace = _operational_planner_service().weekly_review(anchor_date)
        return render_template(
            "planning_weekly_review.html",
            active_page="planning",
            workspace=workspace,
            error_message="",
        )
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/review/week/<anchor_date>")
def planning_weekly_review_save(anchor_date):
    try:
        payload = {
            "what_worked": request.form.get("what_worked", ""),
            "what_failed": request.form.get("what_failed", ""),
            "remove_next_week": request.form.get("remove_next_week", ""),
            "next_priority_1": request.form.get("next_priority_1", ""),
            "next_priority_2": request.form.get("next_priority_2", ""),
            "next_priority_3": request.form.get("next_priority_3", ""),
        }
        _operational_planner_service().save_weekly_review(
            anchor_date,
            payload,
            close=request.form.get("action") == "close",
        )
        return redirect(
            url_for("web.planning_weekly_review", anchor_date=anchor_date),
            code=303,
        )
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/calendar/assessments/<assessment_id>/schedule")
def calendar_assessment_schedule(assessment_id):
    try:
        _operational_planner_service().schedule_assessment(
            assessment_id,
            due_on=request.form.get("due_on", ""),
            start_time=request.form.get("start_time", ""),
            end_time=request.form.get("end_time", ""),
            venue=request.form.get("venue", ""),
        )
        return redirect(
            url_for(
                "web.calendar",
                view="day",
                date=request.form.get("due_on", ""),
                scheduled="1",
            ),
            code=303,
        )
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.get("/notes")
def notes():
    """Render ANVAYA personal Notes, independent from the Obsidian workspace."""
    if _legacy_notes_get_override_configured():
        query = {
            "search": request.args.get("q", "", type=str),
            "topic": request.args.get("topic", "", type=str),
            "difficulty": request.args.get("difficulty", "", type=str),
        }
        service = _notes_resources_service()
        workspace = _safe_notes_workspace(service, query)
        return render_template(
            "notes.html",
            active_page="notes",
            dashboard=workspace,
            error_message="",
        )

    # Preserve Phase 7.5.15 injected-library tests/hosts without making the
    # old Obsidian-backed reader the production default.
    if current_app.config.get("NOTES_STUDIO_LIBRARY_SERVICE_FACTORY") is not None:
        query = {
            "search": request.args.get("q", "", type=str),
            "course": request.args.get("course", "", type=str),
            "note_type": request.args.get("type", "", type=str),
            "tag": request.args.get("tag", "", type=str),
            "view": request.args.get("view", "active", type=str),
            "pinned": request.args.get("pinned", "", type=str),
        }
        try:
            workspace = _notes_studio_library_service().workspace(**query)
        except Exception as error:
            current_app.logger.warning(
                "Compatibility Notes Studio library unavailable (%s).",
                type(error).__name__,
            )
            workspace = unavailable_notes_studio_library()
            workspace["query"] = dict(query)
        return render_template(
            "notes_library.html",
            active_page="notes",
            dashboard=workspace,
            error_message="",
        )

    query = {
        "search": request.args.get("q", "", type=str),
        "course": request.args.get("course", "", type=str),
        "kind": request.args.get("kind", "", type=str),
    }
    try:
        workspace = _anvaya_notes_service().library(**query)
        error_message = ""
    except Exception as error:
        current_app.logger.warning(
            "ANVAYA personal Notes unavailable (%s).",
            type(error).__name__,
        )
        workspace = {
            "available": False,
            "cards": [],
            "summary": {"total": 0, "typed": 0, "handwritten": 0},
            "query": dict(query),
            "filter_options": {"courses": [], "kinds": []},
        }
        error_message = "Your personal Notes library is temporarily unavailable."

    return render_template(
        "anvaya_notes_library.html",
        active_page="notes",
        dashboard=workspace,
        error_message=error_message,
    )


def _native_note_form_payload():
    return {
        "title": request.form.get("title", ""),
        "course": request.form.get("course", ""),
        "key_points": request.form.get("key_points", ""),
        "card_style": request.form.get("card_style", "iris"),
        "body": request.form.get("body", ""),
        "remove_asset_ids": request.form.getlist("remove_asset_ids"),
    }


def _native_note_uploads():
    uploads = []
    for item in request.files.getlist("files"):
        if item is None or not item.filename:
            continue
        uploads.append((str(item.filename), item.read(50 * 1024 * 1024 + 1)))
    return tuple(uploads)


def _native_note_editor_view(payload=None, *, note_id=""):
    payload = dict(payload or {})
    return {
        "id": str(note_id or ""),
        "title": str(payload.get("title") or ""),
        "course": str(payload.get("course") or ""),
        "card_style": str(payload.get("card_style") or "iris"),
        "key_points_text": str(payload.get("key_points") or ""),
        "body": str(payload.get("body") or ""),
        "updated_at": str(payload.get("expected_updated_at") or ""),
        "assets": [],
    }


@web_blueprint.get("/notes/create")
def anvaya_notes_create():
    return render_template(
        "anvaya_notes_create.html",
        active_page="notes",
    )


@web_blueprint.get("/notes/create/typed")
def anvaya_notes_typed():
    return render_template(
        "anvaya_notes_editor.html",
        active_page="notes",
        editor=_native_note_editor_view(),
        error_message="",
    )


@web_blueprint.post("/notes/create/typed")
def anvaya_notes_typed_create():
    service = _anvaya_notes_service()
    payload = _native_note_form_payload()
    try:
        result = service.create_typed_note(payload, _native_note_uploads())
        return redirect(
            url_for("web.anvaya_note_reader", note_id=result["id"]),
            code=303,
        )
    except AnvayaNotesValidationError:
        return (
            render_template(
                "anvaya_notes_editor.html",
                active_page="notes",
                editor=_native_note_editor_view(payload),
                error_message="Check the note name, media settings, ZIP contents, and attached files.",
            ),
            400,
        )
    except AnvayaNotesUnavailableError:
        return (
            render_template(
                "anvaya_notes_editor.html",
                active_page="notes",
                editor=_native_note_editor_view(payload),
                error_message="The note could not be saved. Existing Notes were not changed.",
            ),
            503,
        )


@web_blueprint.get("/notes/create/upload")
def anvaya_notes_upload():
    return render_template(
        "anvaya_notes_upload.html",
        active_page="notes",
        form={"title": "", "course": "", "key_points": "", "card_style": "iris"},
        error_message="",
    )


@web_blueprint.post("/notes/create/upload")
def anvaya_notes_upload_create():
    service = _anvaya_notes_service()
    payload = _native_note_form_payload()
    try:
        result = service.create_handwritten_note(payload, _native_note_uploads())
        return redirect(
            url_for("web.anvaya_note_reader", note_id=result["id"]),
            code=303,
        )
    except AnvayaNotesValidationError:
        return (
            render_template(
                "anvaya_notes_upload.html",
                active_page="notes",
                form=payload,
                error_message="Choose a note name and valid PDF/JPG/PNG pages or a safe ZIP batch.",
            ),
            400,
        )
    except AnvayaNotesUnavailableError:
        return (
            render_template(
                "anvaya_notes_upload.html",
                active_page="notes",
                form=payload,
                error_message="The handwritten note could not be saved.",
            ),
            503,
        )


@web_blueprint.get("/notes/view/<note_id>")
def anvaya_note_reader(note_id):
    try:
        note = _anvaya_notes_service().reader(note_id)
        return render_template(
            "anvaya_notes_reader.html",
            active_page="notes",
            note=note,
            error_message="",
        )
    except AnvayaNotesNotFoundError:
        return (
            render_template(
                "anvaya_notes_reader.html",
                active_page="notes",
                note=None,
                error_message="That personal note was not found.",
            ),
            404,
        )
    except AnvayaNotesUnavailableError:
        return (
            render_template(
                "anvaya_notes_reader.html",
                active_page="notes",
                note=None,
                error_message="That personal note could not be read safely.",
            ),
            503,
        )


@web_blueprint.post("/notes/view/<note_id>/companion")
def anvaya_note_companion_add(note_id):
    try:
        kind = request.form.get("kind", "")
        _anvaya_notes_service().add_companion_entry(
            note_id,
            kind=kind,
            text=request.form.get("entry_text", ""),
            expected_updated_at=request.form.get("expected_updated_at", ""),
        )
        return redirect(
            url_for("web.anvaya_note_reader", note_id=note_id, study_tools="1",
                    study_tab="doubts" if kind == "doubt" else "saved"),
            code=303,
        )
    except AnvayaNotesConflictError:
        return "This note changed since you opened it. Refresh before saving Study Tools.", 409
    except AnvayaNotesNotFoundError:
        return "That note or Study Tools entry was not found.", 404
    except AnvayaNotesValidationError:
        return "Enter a valid Saved note or Doubt.", 400
    except AnvayaNotesUnavailableError:
        return "Study Tools could not be saved.", 503


@web_blueprint.post("/notes/view/<note_id>/companion/<entry_id>/archive")
def anvaya_note_companion_archive(note_id, entry_id):
    try:
        _anvaya_notes_service().archive_companion_entry(
            note_id,
            entry_id=entry_id,
            expected_updated_at=request.form.get("expected_updated_at", ""),
        )
        return redirect(
            url_for("web.anvaya_note_reader", note_id=note_id, study_tools="1",
                    study_tab="doubts" if request.form.get("study_tab") == "doubts" else "saved"),
            code=303,
        )
    except AnvayaNotesConflictError:
        return "This note changed since you opened it. Refresh before archiving.", 409
    except AnvayaNotesNotFoundError:
        return "That note or Study Tools entry was not found.", 404
    except AnvayaNotesValidationError:
        return "Choose a valid Study Tools entry.", 400
    except AnvayaNotesUnavailableError:
        return "Study Tools could not be updated.", 503


@web_blueprint.get("/notes/edit/<note_id>")
def anvaya_note_edit(note_id):
    try:
        editor = _anvaya_notes_service().edit_view(note_id)
        return render_template(
            "anvaya_notes_editor.html",
            active_page="notes",
            editor=editor,
            error_message="",
        )
    except AnvayaNotesNotFoundError:
        return "That personal note was not found.", 404
    except AnvayaNotesUnavailableError:
        return "That personal note is temporarily unavailable.", 503


@web_blueprint.post("/notes/edit/<note_id>")
def anvaya_note_edit_save(note_id):
    service = _anvaya_notes_service()
    payload = _native_note_form_payload()
    payload["expected_updated_at"] = request.form.get("expected_updated_at", "")
    try:
        result = service.update_note(note_id, payload, _native_note_uploads())
        return redirect(
            url_for("web.anvaya_note_reader", note_id=result["id"]),
            code=303,
        )
    except AnvayaNotesConflictError:
        return "This note changed since you opened it. Refresh before saving.", 409
    except AnvayaNotesNotFoundError:
        return "That personal note was not found.", 404
    except AnvayaNotesValidationError:
        return "Check the note fields, media settings, ZIP contents, and attached files.", 400
    except AnvayaNotesUnavailableError:
        return "The personal note could not be saved.", 503


@web_blueprint.get("/notes/file/<note_id>/<asset_id>")
def anvaya_note_file(note_id, asset_id):
    try:
        item = _anvaya_notes_service().read_asset(note_id, asset_id)
        response = current_app.response_class(
            item["bytes"],
            status=200,
            mimetype=str(item["mimetype"]),
        )
        response.headers["Content-Disposition"] = 'inline; filename="{}"'.format(
            str(item["filename"]).replace('"', "")
        )
        response.headers["Cache-Control"] = "private, max-age=300"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'none'"
        return response
    except AnvayaNotesNotFoundError:
        return "Note file not found.", 404
    except AnvayaNotesUnavailableError:
        return "Note file temporarily unavailable.", 503


@web_blueprint.get("/notes/reconciliation")
def notes_reconciliation():
    """Compatibility-only preview from the retired Obsidian-backed Notes bridge."""
    if not _compat_factory_configured("NOTES_STUDIO_RECONCILIATION_SERVICE_FACTORY"):
        return redirect(url_for("web.notes"), code=303)
    try:
        report = _notes_studio_reconciliation_service().report()
        return render_template(
            "notes_reconciliation.html",
            active_page="notes",
            report=report,
            error_message="",
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio reconciliation unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_reconciliation.html",
                active_page="notes",
                report=None,
                error_message="Notes Studio reconciliation is temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.post("/notes/lifecycle")
def notes_lifecycle():
    """Compatibility-only lifecycle command from the retired vault-backed Notes UI."""
    if not _compat_factory_configured("NOTES_STUDIO_LIFECYCLE_SERVICE_FACTORY"):
        return "This retired Notes lifecycle endpoint is unavailable.", 410
    try:
        result = _notes_studio_lifecycle_service().apply_action(
            note_id=request.form.get("note_id", ""),
            action=request.form.get("action", ""),
            expected_hash=request.form.get("expected_hash", ""),
        )
        if result.get("trashed"):
            return redirect(url_for("web.notes_trash"), code=303)
        return redirect(
            url_for(
                "web.notes_reader",
                path=result.get("relative_path")
                or request.form.get("path", ""),
            ),
            code=303,
        )
    except NotesStudioLifecycleConflictError:
        return (
            "This note changed since you opened it. Refresh before continuing.",
            409,
        )
    except NotesStudioLifecycleValidationError:
        return "Choose a supported note action and try again.", 400
    except NotesStudioLifecycleNotFoundError:
        return "That managed note no longer exists.", 404
    except NotesStudioLifecycleUnavailableError:
        return "The note action could not be completed safely.", 503


@web_blueprint.get("/notes/trash")
def notes_trash():
    """Compatibility-only Trash view from the retired vault-backed Notes UI."""
    if not _compat_factory_configured("NOTES_STUDIO_LIFECYCLE_SERVICE_FACTORY"):
        return redirect(url_for("web.notes"), code=303)
    try:
        workspace = _notes_studio_lifecycle_service().trash_workspace()
        return render_template(
            "notes_trash.html",
            active_page="notes",
            workspace=workspace,
            error_message="",
        )
    except NotesStudioLifecycleUnavailableError:
        return (
            render_template(
                "notes_trash.html",
                active_page="notes",
                workspace={"notes": [], "count": 0},
                error_message="Notes Studio Trash is temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.post("/notes/restore")
def notes_restore():
    """Compatibility-only restore command from the retired vault-backed Notes UI."""
    if not _compat_factory_configured("NOTES_STUDIO_LIFECYCLE_SERVICE_FACTORY"):
        return "This retired Notes restore endpoint is unavailable.", 410
    try:
        result = _notes_studio_lifecycle_service().restore_note(
            note_id=request.form.get("note_id", ""),
            expected_hash=request.form.get("expected_hash", ""),
            relative_path=request.form.get("relative_path", ""),
        )
        return redirect(
            url_for("web.notes_reader", path=result["relative_path"]),
            code=303,
        )
    except NotesStudioLifecycleConflictError:
        return (
            "This note or restore destination changed. Refresh Trash before restoring.",
            409,
        )
    except NotesStudioLifecycleValidationError:
        return "Choose a safe vault-relative restore destination.", 400
    except NotesStudioLifecycleNotFoundError:
        return "That trashed note no longer exists.", 404
    except NotesStudioLifecycleUnavailableError:
        return "The note could not be restored safely.", 503


def _notes_editor_form_view(mode):
    return {
        "mode": mode,
        "title": request.form.get("title", ""),
        "body": request.form.get("body", ""),
        "note_type": request.form.get("note_type", "note"),
        "topic": request.form.get("topic", ""),
        "course": request.form.get("course", ""),
        "note_date": request.form.get("note_date", ""),
        "card_summary": request.form.get("card_summary", ""),
        "tags": request.form.get("tags", ""),
        "revision_status": request.form.get("revision_status", "unreviewed"),
        "template_id": request.form.get("template_id", ""),
        "relative_path": request.form.get("relative_path", ""),
        "note_id": request.form.get("note_id", ""),
        "expected_hash": request.form.get("expected_hash", ""),
        "attachment_reference": "",
    }


def _render_notes_editor_error(view, message, status):
    return (
        render_template(
            "notes_editor.html",
            active_page="notes",
            editor=view,
            error_message=message,
        ),
        status,
    )


@web_blueprint.get("/notes/new")
def notes_new():
    """Compatibility alias; production Notes creation uses the independent store."""
    if not _compat_factory_configured("NOTES_STUDIO_EDITOR_SERVICE_FACTORY"):
        return redirect(url_for("web.anvaya_notes_create"), code=303)
    try:
        editor = _notes_studio_editor_service().new_note_view(
            request.args.get("template", "", type=str)
        )
        return render_template(
            "notes_editor.html",
            active_page="notes",
            editor=editor,
            error_message="",
        )
    except NotesStudioEditorNotFoundError:
        return _render_notes_editor_error(
            _notes_editor_form_view("create"),
            "That note template was not found.",
            404,
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio editor unavailable (%s).",
            type(error).__name__,
        )
        return _render_notes_editor_error(
            _notes_editor_form_view("create"),
            "Notes Studio editing is temporarily unavailable.",
            503,
        )


@web_blueprint.post("/notes/new")
def notes_new_create():
    """Compatibility-only old vault-backed note creation."""
    if not _compat_factory_configured("NOTES_STUDIO_EDITOR_SERVICE_FACTORY"):
        return "The old vault-backed Notes creation endpoint is retired.", 410
    service = _notes_studio_editor_service()
    try:
        result = service.create_note(request.form)
        return redirect(
            url_for("web.notes_reader", path=result["relative_path"]),
            code=303,
        )
    except NotesStudioEditorValidationError:
        return _render_notes_editor_error(
            _notes_editor_form_view("create"),
            "Check the note fields and try again.",
            400,
        )
    except NotesStudioEditorUnavailableError:
        return _render_notes_editor_error(
            _notes_editor_form_view("create"),
            "The note could not be created. Existing notes were not changed.",
            503,
        )


@web_blueprint.get("/notes/edit")
def notes_edit():
    """Compatibility-only old vault-backed note editor."""
    if not _compat_factory_configured("NOTES_STUDIO_EDITOR_SERVICE_FACTORY"):
        path = request.args.get("path", "", type=str)
        return redirect(url_for("web.obsidian_note", path=path), code=303)
    try:
        editor = _notes_studio_editor_service().edit_view(
            request.args.get("path", "", type=str),
            attachment_reference=request.args.get("attachment", "", type=str),
        )
        return render_template(
            "notes_editor.html",
            active_page="notes",
            editor=editor,
            error_message="",
        )
    except NotesStudioEditorNotFoundError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "That note is not available for Notes Studio editing.",
            404,
        )
    except NotesStudioEditorUnavailableError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "The note could not be opened safely for editing.",
            503,
        )


@web_blueprint.post("/notes/edit")
def notes_edit_save():
    """Compatibility-only old vault-backed note update."""
    if not _compat_factory_configured("NOTES_STUDIO_EDITOR_SERVICE_FACTORY"):
        return "The old vault-backed Notes editor is retired.", 410
    service = _notes_studio_editor_service()
    try:
        result = service.update_note(request.form)
        return redirect(
            url_for("web.notes_reader", path=result["relative_path"]),
            code=303,
        )
    except NotesStudioEditorConflictError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "This note changed since you opened it. Refresh the note before saving.",
            409,
        )
    except NotesStudioEditorValidationError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "Check the note fields and try again.",
            400,
        )
    except NotesStudioEditorNotFoundError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "That managed note no longer exists.",
            404,
        )
    except NotesStudioEditorUnavailableError:
        return _render_notes_editor_error(
            _notes_editor_form_view("edit"),
            "The note could not be saved. Existing note content was not overwritten.",
            503,
        )


@web_blueprint.post("/notes/attachments")
def notes_attachment_upload():
    """Compatibility-only old vault-backed attachment upload."""
    if not _compat_factory_configured("NOTES_STUDIO_EDITOR_SERVICE_FACTORY"):
        return "The old vault-backed Notes attachment endpoint is retired.", 410
    service = _notes_studio_editor_service()
    file_item = request.files.get("file")
    filename = "" if file_item is None else str(file_item.filename or "")
    payload = b"" if file_item is None else file_item.read(10 * 1024 * 1024 + 1)
    try:
        result = service.upload_attachment(
            note_id=request.form.get("note_id", ""),
            expected_hash=request.form.get("expected_hash", ""),
            filename=filename,
            payload=payload,
        )
        return redirect(
            url_for(
                "web.notes_edit",
                path=result["note_relative_path"],
                attachment=result["markdown_reference"],
            ),
            code=303,
        )
    except NotesStudioEditorConflictError:
        return "The note changed since you opened it. Refresh before attaching an image.", 409
    except NotesStudioEditorValidationError:
        return "Choose a valid PNG, JPEG, GIF, or WebP image smaller than 10 MB.", 400
    except NotesStudioEditorNotFoundError:
        return "That managed note no longer exists.", 404
    except NotesStudioEditorUnavailableError:
        return "The image could not be attached. Existing notes were not changed.", 503


@web_blueprint.get("/notes/asset")
def notes_asset():
    """Compatibility-only old vault-backed Notes asset."""
    if not _compat_factory_configured("NOTES_STUDIO_ASSET_SERVICE_FACTORY"):
        return "The old vault-backed Notes asset endpoint is retired.", 410
    try:
        payload = _notes_studio_asset_service().read_asset(
            request.args.get("path", "", type=str)
        )
        response = current_app.response_class(
            payload["bytes"],
            status=200,
            mimetype=str(payload["mimetype"]),
        )
        response.headers["Cache-Control"] = "private, max-age=300"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'"
        return response
    except NotesStudioAssetNotFoundError as error:
        current_app.logger.warning(
            "Notes Studio asset not found (%s).",
            type(error).__name__,
        )
        response = current_app.response_class(
            "Image not found.",
            status=404,
            mimetype="text/plain",
        )
    except NotesStudioAssetUnavailableError as error:
        current_app.logger.warning(
            "Notes Studio asset unavailable (%s).",
            type(error).__name__,
        )
        response = current_app.response_class(
            "Image temporarily unavailable.",
            status=503,
            mimetype="text/plain",
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio asset unavailable (%s).",
            type(error).__name__,
        )
        response = current_app.response_class(
            "Image temporarily unavailable.",
            status=503,
            mimetype="text/plain",
        )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@web_blueprint.get("/notes/templates")
def notes_templates():
    """Compatibility alias; production templates are visual card styles."""
    if not _compat_factory_configured("NOTES_STUDIO_TEMPLATE_SERVICE_FACTORY"):
        return redirect(url_for("web.anvaya_notes_create"), code=303)
    try:
        templates = _notes_studio_template_service().list_templates()
        return render_template(
            "notes_templates.html",
            active_page="notes",
            templates=templates,
            error_message="",
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio templates unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_templates.html",
                active_page="notes",
                templates=[],
                error_message="Academic note templates are temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.get("/notes/templates/<template_id>")
def notes_template_preview(template_id):
    """Compatibility-only preview for retired Markdown scaffolds."""
    if not _compat_factory_configured("NOTES_STUDIO_TEMPLATE_SERVICE_FACTORY"):
        return redirect(url_for("web.anvaya_notes_create"), code=303)
    try:
        template = _notes_studio_template_service().template_view(template_id)
        return render_template(
            "notes_template_preview.html",
            active_page="notes",
            template=template,
            error_message="",
        )
    except NotesStudioTemplateNotFoundError as error:
        current_app.logger.warning(
            "Notes Studio template not found (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_template_preview.html",
                active_page="notes",
                template=None,
                error_message="Template not found.",
            ),
            404,
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio template preview unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_template_preview.html",
                active_page="notes",
                template=None,
                error_message="This template preview is temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.get("/notes/note")
def notes_reader():
    """Compatibility alias; vault Markdown belongs to the Obsidian product."""
    if not _compat_factory_configured("NOTES_STUDIO_READER_SERVICE_FACTORY"):
        return redirect(
            url_for(
                "web.obsidian_note",
                path=request.args.get("path", "", type=str),
            ),
            code=303,
        )
    try:
        note = _notes_studio_reader_service().reader_view(
            request.args.get("path", "", type=str)
        )
        return render_template(
            "notes_reader.html",
            active_page="notes",
            note=note,
            error_message="",
        )
    except NotesStudioReadNotFoundError as error:
        current_app.logger.warning(
            "Notes Studio Reader note not found (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_reader.html",
                active_page="notes",
                note=None,
                error_message="That Markdown note was not found in the current Notes Studio vault.",
            ),
            404,
        )
    except NotesStudioReadUnavailableError as error:
        current_app.logger.warning(
            "Notes Studio Reader unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_reader.html",
                active_page="notes",
                note=None,
                error_message="The note changed or could not be read safely. Refresh Notes Studio and try again.",
            ),
            503,
        )
    except Exception as error:
        current_app.logger.warning(
            "Notes Studio Reader unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "notes_reader.html",
                active_page="notes",
                note=None,
                error_message="The note changed or could not be read safely. Refresh Notes Studio and try again.",
            ),
            503,
        )


@web_blueprint.post("/notes")
def notes_create():
    """Create a note through the operational service boundary."""
    service = _notes_resources_service()
    try:
        service.create_note(
            request.form.get("title", ""),
            request.form.get("topic", ""),
            request.form.get("difficulty", ""),
            request.form.get("content", ""),
        )
        return redirect(url_for("web.notes", created="1"), code=303)
    except NotesResourcesWebValidationError:
        return _render_notes_command_error(
            service,
            "Enter a title before saving the note.",
            400,
        )
    except NotesResourcesWebUnavailableError:
        return _render_notes_command_error(
            service,
            "The note could not be saved. Your existing notes were not changed.",
            503,
        )


@web_blueprint.post("/notes/<int:position>")
def notes_update(position):
    """Update one note by its current 1-based position."""
    service = _notes_resources_service()
    try:
        service.update_note(
            position,
            request.form.get("title", ""),
            request.form.get("topic", ""),
            request.form.get("difficulty", ""),
            request.form.get("content", ""),
        )
        return redirect(url_for("web.notes", updated="1"), code=303)
    except NotesResourcesWebValidationError:
        return _render_notes_command_error(service, "The note update is invalid.", 400)
    except NotesResourcesWebNotFoundError:
        return _render_notes_command_error(service, "That note no longer exists.", 404)
    except NotesResourcesWebUnavailableError:
        return _render_notes_command_error(
            service,
            "The note could not be updated. Your existing notes were not changed.",
            503,
        )


@web_blueprint.get("/resources")
def resources():
    """Render the operational Resources workspace."""
    query = {
        "search": request.args.get("q", "", type=str),
        "type": request.args.get("type", "", type=str),
        "status": request.args.get("status", "", type=str),
    }
    service = _notes_resources_service()
    workspace = _safe_resources_workspace(service, query)
    return render_template(
        "resources.html",
        active_page="resources",
        dashboard=workspace,
        error_message="",
    )


@web_blueprint.post("/resources")
def resources_create():
    """Create a resource through the operational service boundary."""
    service = _notes_resources_service()
    try:
        service.create_resource(
            request.form.get("title", ""),
            request.form.get("resource_type", ""),
            request.form.get("link", ""),
        )
        return redirect(url_for("web.resources", created="1"), code=303)
    except NotesResourcesWebValidationError:
        return _render_resources_command_error(
            service,
            "Enter a title before adding the resource.",
            400,
        )
    except NotesResourcesWebUnavailableError:
        return _render_resources_command_error(
            service,
            "The resource could not be saved. Your existing resources were not changed.",
            503,
        )


@web_blueprint.post("/resources/<int:position>/status")
def resources_update_status(position):
    """Update one resource learning status by its current 1-based position."""
    service = _notes_resources_service()
    try:
        service.update_resource_status(position, request.form.get("status", ""))
        return redirect(url_for("web.resources", updated="1"), code=303)
    except NotesResourcesWebValidationError:
        return _render_resources_command_error(
            service,
            "Choose a valid resource status.",
            400,
        )
    except NotesResourcesWebNotFoundError:
        return _render_resources_command_error(
            service,
            "That resource no longer exists.",
            404,
        )
    except NotesResourcesWebUnavailableError:
        return _render_resources_command_error(
            service,
            "The resource status could not be updated. Your existing resources were not changed.",
            503,
        )


@web_blueprint.get("/obsidian")
def obsidian():
    """Render the live read-only Obsidian workspace."""
    query = request.args.get("q", "", type=str)
    service = _obsidian_workspace_service()
    notice_message = ""
    if request.args.get("connected") == "1":
        notice_message = "Obsidian vault connected."
    elif request.args.get("enabled") == "1":
        notice_message = "Obsidian vault enabled."
    elif request.args.get("disabled") == "1":
        notice_message = "Obsidian vault disabled."
    try:
        dashboard = service.workspace(query)
        status = 200
    except ObsidianWorkspaceUnavailableError as error:
        current_app.logger.warning(
            "Obsidian workspace unavailable (%s).",
            type(error).__name__,
        )
        dashboard = unavailable_obsidian_workspace()
        status = 503
    except Exception as error:
        current_app.logger.warning(
            "Obsidian workspace unavailable (%s).",
            type(error).__name__,
        )
        dashboard = unavailable_obsidian_workspace()
        status = 503
    return (
        render_template(
            "obsidian.html",
            active_page="obsidian",
            dashboard=dashboard,
            error_message="",
            notice_message=notice_message,
        ),
        status,
    )


@web_blueprint.get("/obsidian/note")
def obsidian_note():
    """Render one current Markdown note without mutating history or the vault."""
    try:
        service = _obsidian_study_service()
        note = service.reader_view(request.args.get("path", "", type=str))
        return render_template(
            "obsidian_note.html",
            active_page="obsidian",
            note=note,
            error_message="",
        )
    except (
        ObsidianWorkspaceValidationError,
        ObsidianWorkspaceNotFoundError,
        ObsidianWorkspaceUnavailableError,
        ObsidianStudyValidationError,
        ObsidianStudyNotFoundError,
        ObsidianStudyConflictError,
        ObsidianStudyUnavailableError,
    ) as error:
        status, _code = _study_error_status(error)
        messages = {
            400: "Choose a valid Markdown note inside the configured vault.",
            404: "That Markdown note was not found in the current vault.",
            409: "The note changed. Refresh the Reader and try again.",
            503: "The note changed or could not be read safely. Refresh the Obsidian workspace and try again.",
        }
        current_app.logger.warning(
            "Obsidian Reader unavailable (%s).",
            type(error).__name__,
        )
        return _render_obsidian_note_error(messages[status], status)
    except Exception as error:
        current_app.logger.warning(
            "Obsidian Reader unavailable (%s).",
            type(error).__name__,
        )
        return _render_obsidian_note_error(
            "The note changed or could not be read safely. Refresh the Obsidian workspace and try again.",
            503,
        )


@web_blueprint.post("/obsidian/note/reading/start")
def obsidian_reading_start():
    """Start an explicit browser-owned active-reading session."""
    try:
        payload = _tracking_payload(("path", "source_hash"))
        result = _obsidian_study_service().start_reading(
            relative_path=payload["path"],
            source_hash=payload["source_hash"],
        )
        return jsonify(ok=True, **result), 201
    except (
        ObsidianStudyValidationError,
        ObsidianStudyNotFoundError,
        ObsidianStudyConflictError,
        ObsidianStudyUnavailableError,
    ) as error:
        return _tracking_error(error)
    except Exception as error:
        return _tracking_error(error)


def _reading_update(command_name, *, include_replayed_delta=False):
    try:
        payload = _tracking_payload(
            (
                "path",
                "source_hash",
                "session_id",
                "sequence",
                "delta_seconds",
                "scroll_bps",
            )
        )
        command = getattr(_obsidian_study_service(), command_name)
        command_values = {
            "relative_path": payload["path"],
            "source_hash": payload["source_hash"],
            "session_id": payload["session_id"],
            "sequence": payload["sequence"],
            "delta_seconds": payload["delta_seconds"],
            "scroll_bps": payload["scroll_bps"],
        }
        if include_replayed_delta:
            command_values["replayed_delta_seconds"] = payload.get(
                "replayed_delta_seconds"
            )
        result = command(
            **command_values
        )
        return jsonify(ok=True, **result), 200
    except (
        ObsidianStudyValidationError,
        ObsidianStudyNotFoundError,
        ObsidianStudyConflictError,
        ObsidianStudyUnavailableError,
    ) as error:
        return _tracking_error(error)
    except Exception as error:
        return _tracking_error(error)


@web_blueprint.post("/obsidian/note/reading/heartbeat")
def obsidian_reading_heartbeat():
    """Accept one bounded active-reading heartbeat."""
    return _reading_update("heartbeat")


@web_blueprint.post("/obsidian/note/reading/end")
def obsidian_reading_end():
    """End an active-reading session with one final bounded delta."""
    return _reading_update("end_reading", include_replayed_delta=True)


def _add_companion_entry(entry_type, saved_label):
    relative_path = request.form.get("path", "")
    try:
        _obsidian_study_service().add_companion_entry(
            relative_path=relative_path,
            source_hash=request.form.get("source_hash", ""),
            entry_type=entry_type,
            entry_text=request.form.get("entry_text", ""),
        )
        return _companion_redirect(relative_path, saved_label,
                                   "doubts" if entry_type == "doubt" else "saved")
    except (
        ObsidianStudyValidationError,
        ObsidianStudyNotFoundError,
        ObsidianStudyConflictError,
        ObsidianStudyUnavailableError,
    ) as error:
        return _companion_error(error)
    except Exception as error:
        return _companion_error(error)


@web_blueprint.post("/obsidian/note/companion/key-points")
def obsidian_companion_key_point():
    """Persist one user-authored key point, then return to the Reader."""
    return _add_companion_entry("key_point", "key_point")


@web_blueprint.post("/obsidian/note/companion/doubts")
def obsidian_companion_doubt():
    """Persist one user-authored doubt, then return to the Reader."""
    return _add_companion_entry("doubt", "doubt")


@web_blueprint.post("/obsidian/note/companion/<entry_id>/archive")
def obsidian_companion_archive(entry_id):
    """Archive one Companion entry scoped to the current note."""
    relative_path = request.form.get("path", "")
    try:
        _obsidian_study_service().archive_companion_entry(
            relative_path=relative_path,
            source_hash=request.form.get("source_hash", ""),
            entry_id=entry_id,
        )
        return _companion_redirect(relative_path, "archived",
                                   "doubts" if request.form.get("study_tab") == "doubts" else "saved")
    except (
        ObsidianStudyValidationError,
        ObsidianStudyNotFoundError,
        ObsidianStudyConflictError,
        ObsidianStudyUnavailableError,
    ) as error:
        return _companion_error(error)
    except Exception as error:
        return _companion_error(error)


@web_blueprint.post("/obsidian/connect")
def obsidian_connect():
    """Connect or change the configured vault using explicit POST + PRG."""
    service = _obsidian_workspace_service()
    try:
        service.connect_vault(request.form.get("vault_path", ""))
        return redirect(url_for("web.obsidian", connected="1"), code=303)
    except ObsidianWorkspaceValidationError:
        return _render_obsidian_command_error(
            service,
            "Choose an existing Obsidian vault folder containing a .obsidian directory.",
            400,
        )
    except ObsidianWorkspaceUnavailableError:
        return _render_obsidian_command_error(
            service,
            "Obsidian configuration could not be updated. Your vault was not changed.",
            503,
        )


@web_blueprint.post("/obsidian/enable")
def obsidian_enable():
    """Enable the existing configured vault using explicit POST + PRG."""
    service = _obsidian_workspace_service()
    try:
        service.enable_vault()
        return redirect(url_for("web.obsidian", enabled="1"), code=303)
    except ObsidianWorkspaceValidationError:
        return _render_obsidian_command_error(
            service,
            "Reconnect a valid Obsidian vault before enabling it.",
            400,
        )
    except ObsidianWorkspaceUnavailableError:
        return _render_obsidian_command_error(
            service,
            "Obsidian configuration could not be updated. Your vault was not changed.",
            503,
        )


@web_blueprint.post("/obsidian/disable")
def obsidian_disable():
    """Disable Obsidian configuration without touching Markdown."""
    service = _obsidian_workspace_service()
    try:
        service.disable_vault()
        return redirect(url_for("web.obsidian", disabled="1"), code=303)
    except ObsidianWorkspaceUnavailableError:
        return _render_obsidian_command_error(
            service,
            "Obsidian configuration could not be updated. Your vault was not changed.",
            503,
        )


@web_blueprint.get("/knowledge")
def knowledge():
    """Search current study material without mutating the retrieval index."""
    query = request.args.get("q", "", type=str)

    # Preserve the Phase 7.5.8 injected-provider contract for regression tests
    # and explicit diagnostic embeddings. Normal ANVAYA does not set this
    # provider, so production continues into Unified Study Search below.
    if current_app.config.get("KNOWLEDGE_DASHBOARD_PROVIDER") is not None:
        dashboard = dict(_knowledge_dashboard(query))
        dashboard["legacy_phase758"] = True
        return render_template("knowledge.html", active_page="knowledge", dashboard=dashboard)

    course_id = request.args.get("course_id", "", type=str).strip()
    topic_id = request.args.get("topic_id", "", type=str).strip()
    source_type = request.args.get("source_type", "", type=str).strip()
    provider = request.args.get("provider", "", type=str).strip()
    warning = ""
    results = ()
    service = _unified_search_service()
    try:
        filter_options = service.filter_options()
    except Exception:
        filter_options = {
            "courses": (),
            "topics": (),
            "source_types": (),
            "providers": (),
        }

    if str(query or "").strip():
        try:
            results = service.search(
                query,
                course_ids=(course_id,) if course_id else (),
                topic_ids=(topic_id,) if topic_id else (),
                source_types=(source_type,) if source_type else (),
                providers=(provider,) if provider else (),
            )
            warning = str(getattr(service, "last_warning", "") or "")
        except UnifiedSearchStaleIndexError:
            warning = (
                "Learning material changed since the current knowledge index. "
                "Rebuild the index before search or tutor use."
            )
        except UnifiedSearchError:
            warning = (
                "Study search is temporarily unavailable. "
                "Your learning material and index were not changed."
            )

    dashboard = {
        "query": str(query or "").strip(),
        "searched": bool(str(query or "").strip()),
        "results": results,
        "warning": warning,
        "filter_options": filter_options,
        "filters": {
            "course_id": course_id,
            "topic_id": topic_id,
            "source_type": source_type,
            "provider": provider,
        },
        "legacy_phase758": False,
    }
    return render_template("knowledge.html", active_page="knowledge", dashboard=dashboard)


@web_blueprint.get("/api/search/suggest")
def search_suggest():
    try:
        results = _unified_search_service().suggest(
            request.args.get("q", "", type=str),
            limit=8,
        )
        return jsonify(
            results=[
                {
                    "kind": item.kind,
                    "label": item.label,
                    "subtitle": item.subtitle,
                    "value": item.value,
                    "open_target": item.open_target,
                }
                for item in results
            ]
        )
    except Exception:
        return jsonify(results=[]), 200


@web_blueprint.get("/retrieval/diagnostics")
def retrieval_diagnostics():
    return render_template(
        "retrieval_diagnostics.html",
        active_page="knowledge",
        diagnostics=_knowledge_dashboard(""),
    )


@web_blueprint.get("/knowledge/item/<document_id>")
def knowledge_item(document_id):
    try:
        item = _knowledge_reader_service().view(document_id)
        return render_template(
            "knowledge_item.html",
            active_page="knowledge",
            item=item,
        )
    except KnowledgeReaderNotFoundError:
        return "Knowledge source was not found.", 404
    except KnowledgeReaderUnavailableError:
        return "Knowledge source is temporarily unavailable.", 503


def _knowledge_tracking_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("invalid tracking payload")
    return payload


@web_blueprint.post("/knowledge/item/<document_id>/reading/start")
def knowledge_reading_start(document_id):
    try:
        payload = _knowledge_tracking_payload()
        result = _knowledge_reader_service().start_reading(
            document_id=document_id,
            version_hash=payload.get("version_hash", ""),
        )
        return jsonify(ok=True, **result), 201
    except (ValueError, KnowledgeReaderUnavailableError):
        return jsonify(ok=False, error="conflict"), 409
    except KnowledgeReaderNotFoundError:
        return jsonify(ok=False, error="not_found"), 404


@web_blueprint.post("/knowledge/item/<document_id>/reading/heartbeat")
def knowledge_reading_heartbeat(document_id):
    try:
        payload = _knowledge_tracking_payload()
        result = _knowledge_reader_service().heartbeat(
            document_id=document_id,
            version_hash=payload.get("version_hash", ""),
            session_id=payload.get("session_id", ""),
            sequence=payload.get("sequence", 0),
            delta_seconds=payload.get("delta_seconds", 0),
            scroll_bps=payload.get("scroll_bps", 0),
        )
        return jsonify(ok=True, **result), 200
    except (ValueError, KnowledgeReaderUnavailableError):
        return jsonify(ok=False, error="conflict"), 409
    except KnowledgeReaderNotFoundError:
        return jsonify(ok=False, error="not_found"), 404


@web_blueprint.post("/knowledge/item/<document_id>/reading/end")
def knowledge_reading_end(document_id):
    try:
        payload = _knowledge_tracking_payload()
        result = _knowledge_reader_service().end_reading(
            document_id=document_id,
            version_hash=payload.get("version_hash", ""),
            session_id=payload.get("session_id", ""),
            sequence=payload.get("sequence", 0),
            delta_seconds=payload.get("delta_seconds", 0),
            scroll_bps=payload.get("scroll_bps", 0),
            replayed_delta_seconds=payload.get("replayed_delta_seconds", 0),
        )
        return jsonify(ok=True, **result), 200
    except (ValueError, KnowledgeReaderUnavailableError):
        return jsonify(ok=False, error="conflict"), 409
    except KnowledgeReaderNotFoundError:
        return jsonify(ok=False, error="not_found"), 404


@web_blueprint.post("/knowledge/item/<document_id>/companion/<entry_type>")
def knowledge_companion_add(document_id, entry_type):
    try:
        _knowledge_reader_service().add_entry(
            document_id=document_id,
            version_hash=request.form.get("version_hash", ""),
            entry_type=entry_type,
            entry_text=request.form.get("entry_text", ""),
        )
        return redirect(
            url_for("web.knowledge_item", document_id=document_id),
            code=303,
        )
    except ValueError:
        return "Companion entry is invalid.", 400
    except KnowledgeReaderNotFoundError:
        return "Knowledge source was not found.", 404
    except KnowledgeReaderUnavailableError:
        return "Knowledge source changed. Refresh and try again.", 409


@web_blueprint.post("/knowledge/item/<document_id>/companion/<entry_id>/archive")
def knowledge_companion_archive(document_id, entry_id):
    try:
        _knowledge_reader_service().archive_entry(
            document_id=document_id,
            version_hash=request.form.get("version_hash", ""),
            entry_id=entry_id,
        )
        return redirect(
            url_for("web.knowledge_item", document_id=document_id),
            code=303,
        )
    except KnowledgeReaderNotFoundError:
        return "Knowledge source or Companion entry was not found.", 404
    except KnowledgeReaderUnavailableError:
        return "Knowledge source changed. Refresh and try again.", 409


@web_blueprint.post("/knowledge/item/<document_id>/ask")
def knowledge_ask_source(document_id):
    try:
        session_id = _academic_agent_service().create_source_session(
            document_id=document_id,
            version_hash=request.form.get("version_hash", ""),
            prefill_question=request.form.get("prefill_question", ""),
        )
        return redirect(
            url_for("web.academic_agent_session", session_id=session_id),
            code=303,
        )
    except AcademicAgentWebNotFoundError:
        return "Knowledge source was not found.", 404
    except AcademicAgentWebValidationError:
        return "Knowledge source changed. Refresh it before asking ANVAYA.", 409
    except AcademicAgentWebUnavailableError:
        return "Academic Agent is temporarily unavailable.", 503


@web_blueprint.get("/agent")
def academic_agent():
    """Render mentor advice, provider readiness, and recent tutor sessions."""
    course_code = request.args.get("course", "", type=str)
    service = _academic_agent_service()
    try:
        workspace = service.workspace(course_code)
        return render_template(
            "agent.html",
            active_page="agent",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:  # Never expose raw backend/provider details.
        current_app.logger.warning(
            "Academic Agent workspace unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "agent.html",
                active_page="agent",
                workspace=_unavailable_agent_workspace(),
                error_message="",
            ),
            503,
        )


@web_blueprint.post("/agent/sessions")
def academic_agent_create_session():
    """Create tutor conversation scope without invoking the tutor provider."""
    service = _academic_agent_service()
    try:
        session_id = service.create_session(
            course_id=request.form.get("course_id", ""),
            mode=request.form.get("mode", "concept"),
            source_policy=request.form.get("source_policy", "source_only"),
            title=request.form.get("title", ""),
        )
        return redirect(
            url_for("web.academic_agent_session", session_id=session_id),
            code=303,
        )
    except AcademicAgentWebValidationError:
        try:
            workspace = service.workspace("")
        except Exception:
            workspace = _unavailable_agent_workspace()
        return (
            render_template(
                "agent.html",
                active_page="agent",
                workspace=workspace,
                error_message="The selected tutor session settings are invalid.",
            ),
            400,
        )
    except AcademicAgentWebUnavailableError:
        return (
            render_template(
                "agent.html",
                active_page="agent",
                workspace=_unavailable_agent_workspace(),
                error_message="Academic Agent is temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.get("/agent/sessions/<session_id>")
def academic_agent_session(session_id):
    """Reopen a persisted tutor transcript without invoking the provider."""
    service = _academic_agent_service()
    try:
        session = service.session_view(session_id)
        return render_template(
            "agent_session.html",
            active_page="agent",
            session=session,
            error_message="",
        )
    except AcademicAgentWebNotFoundError:
        return _render_session_error(
            service,
            session_id,
            "Tutor session was not found.",
            404,
        )
    except AcademicAgentWebUnavailableError:
        return _render_session_error(
            service,
            session_id,
            "Tutor session history is temporarily unavailable.",
            503,
        )


@web_blueprint.post("/agent/sessions/<session_id>/ask")
def academic_agent_ask(session_id):
    """Run one explicit grounded tutor question and redirect to the transcript."""
    service = _academic_agent_service()
    try:
        service.ask(session_id, request.form.get("question", ""))
        return redirect(
            url_for("web.academic_agent_session", session_id=session_id),
            code=303,
        )
    except AcademicAgentWebValidationError:
        return _render_session_error(
            service,
            session_id,
            "Question cannot be empty or the tutor session is not active.",
            400,
        )
    except AcademicAgentWebNotFoundError:
        return _render_session_error(
            service,
            session_id,
            "Tutor session was not found.",
            404,
        )
    except AcademicAgentWebUnavailableError as error:
        safe_messages = {
            "AI tutor is not configured on this machine.",
            "The AI tutor could not complete this request. Your academic data was not changed.",
            "Grounded academic sources are temporarily unavailable.",
            "Learning material changed. Rebuild the knowledge index before asking ANVAYA.",
            "Tutor session history is temporarily unavailable.",
            "Academic Agent storage is temporarily unavailable.",
        }
        message = str(error)
        if message not in safe_messages:
            message = (
                "The AI tutor could not complete this request. "
                "Your academic data was not changed."
            )
        return _render_session_error(service, session_id, message, 503)


@web_blueprint.get("/healthz")
def healthz():
    """Return a side-effect-free health response for local startup checks."""
    return jsonify(
        phase="7.5.1",
        service="personal-learning-assistant-web",
        status="ok",
    )
