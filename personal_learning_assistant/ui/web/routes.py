"""Routes for the local Personal AI Learning Assistant web UI."""

from __future__ import annotations

from io import BytesIO

from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from personal_learning_assistant.services.academic_agent_web_service import (
    AcademicAgentWebNotFoundError,
    AcademicAgentWebUnavailableError,
    AcademicAgentWebValidationError,
    build_academic_agent_web_service,
)
from personal_learning_assistant.services.alex_handoff_service import (
    AlexHandoffError,
    build_alex_handoff_service,
)
from personal_learning_assistant.services.assessment_dashboard_service import (
    load_assessment_catalogue,
    unavailable_assessment_catalogue,
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
from personal_learning_assistant.services.moodle_sync_service import (
    MoodleSyncError,
    build_moodle_sync_service,
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


def _alex_handoff_service():
    factory = current_app.config.get("ALEX_HANDOFF_SERVICE_FACTORY")
    return factory() if factory is not None else build_alex_handoff_service()


def _academic_agent_service():
    factory = (
        current_app.config.get("ACADEMIC_AGENT_WEB_SERVICE_FACTORY")
        or build_academic_agent_web_service
    )
    return factory()


def _moodle_sync_service():
    factory = current_app.config.get("MOODLE_SYNC_SERVICE_FACTORY")
    return factory() if factory is not None else build_moodle_sync_service()


def _notes_resources_service():
    factory = (
        current_app.config.get("NOTES_RESOURCES_WEB_SERVICE_FACTORY")
        or build_notes_resources_web_service
    )
    return factory()


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


def _companion_redirect(relative_path, result):
    return redirect(
        url_for(
            "web.obsidian_note",
            path=relative_path,
            companion_saved=result,
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


@web_blueprint.get("/courses")
def courses():
    """Render the read-only Courses & Topics catalogue."""
    return render_template("courses.html", active_page="courses", catalogue=_course_catalogue())


@web_blueprint.get("/assessments")
def assessments():
    """Render the read-only assessment timeline."""
    return render_template("assessments.html", active_page="assessments", catalogue=_assessment_catalogue())


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


def _routine_form_payload():
    return {
        "title": request.form.get("title", ""),
        "category": request.form.get("category", "routine"),
        "priority": request.form.get("priority", "P1"),
        "frequency": request.form.get("frequency", "weekly"),
        "weekdays": tuple(request.form.getlist("weekdays")),
        "active_from": request.form.get("active_from", ""),
        "active_to": request.form.get("active_to", ""),
        "start_time": request.form.get("start_time", ""),
        "end_time": request.form.get("end_time", ""),
        "duration_minutes": request.form.get("duration_minutes", ""),
        "preferred_window": request.form.get("preferred_window", ""),
        "preferred_location": request.form.get("preferred_location", ""),
        "condition_text": request.form.get("condition_text", ""),
    }


@web_blueprint.get("/planning/routines")
def planning_routines():
    """Render recurring schedules using the existing routine_templates authority."""
    service = _operational_planner_service()
    try:
        workspace = service.routines_workspace()
        return render_template(
            "planning_routines.html",
            active_page="planning",
            workspace=workspace,
            error_message="",
        )
    except Exception as error:
        current_app.logger.warning(
            "Operational schedules unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "planning_routines.html",
                active_page="planning",
                workspace={
                    "available": False,
                    "routines": (),
                    "summary": {"active": 0, "paused": 0},
                },
                error_message=(
                    "Schedules are temporarily unavailable. "
                    "Existing planner data was not changed."
                ),
            ),
            503,
        )


@web_blueprint.post("/planning/routines")
def planning_routines_create():
    service = _operational_planner_service()
    try:
        service.create_routine(**_routine_form_payload())
        return redirect(url_for("web.planning_routines", created="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        status = _planner_error_status(error)
        try:
            workspace = service.routines_workspace()
        except Exception:
            workspace = {
                "available": False,
                "routines": (),
                "summary": {"active": 0, "paused": 0},
            }
        return (
            render_template(
                "planning_routines.html",
                active_page="planning",
                workspace=workspace,
                error_message=str(error),
            ),
            status,
        )


@web_blueprint.post("/planning/routines/<routine_id>")
def planning_routine_update(routine_id):
    try:
        _operational_planner_service().update_routine(
            routine_id, **_routine_form_payload()
        )
        return redirect(url_for("web.planning_routines", updated="1"), code=303)
    except (
        OperationalPlannerWebValidationError,
        OperationalPlannerWebNotFoundError,
        OperationalPlannerWebConflictError,
        OperationalPlannerWebUnavailableError,
    ) as error:
        return str(error), _planner_error_status(error)


@web_blueprint.post("/planning/routines/<routine_id>/status")
def planning_routine_status(routine_id):
    try:
        _operational_planner_service().set_routine_status(
            routine_id, request.form.get("status", "")
        )
        return redirect(url_for("web.planning_routines", updated="1"), code=303)
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


@web_blueprint.get("/integrations/moodle")
def moodle_integration():
    """Show local Moodle connector status without making a remote request."""
    service = _moodle_sync_service()
    try:
        status = service.status()
        return render_template(
            "moodle_integration.html",
            active_page="integrations",
            status=status,
            preview=None,
            sync_result=None,
            error_message="",
        )
    except Exception as error:
        current_app.logger.warning(
            "Moodle integration status unavailable (%s).",
            type(error).__name__,
        )
        return (
            render_template(
                "moodle_integration.html",
                active_page="integrations",
                status={
                    "configured": False,
                    "migration_ready": False,
                    "root_path": "knowledge/moodle",
                    "recent": (),
                },
                preview=None,
                sync_result=None,
                error_message="Moodle integration storage is temporarily unavailable.",
            ),
            503,
        )


@web_blueprint.post("/integrations/moodle/preview")
def moodle_preview():
    service = _moodle_sync_service()
    try:
        return render_template(
            "moodle_integration.html",
            active_page="integrations",
            status=service.status(),
            preview=service.preview(),
            sync_result=None,
            error_message="",
        )
    except MoodleSyncError as error:
        return (
            render_template(
                "moodle_integration.html",
                active_page="integrations",
                status=service.status(),
                preview=None,
                sync_result=None,
                error_message=str(error),
            ),
            400,
        )


@web_blueprint.post("/integrations/moodle/sync")
def moodle_sync():
    service = _moodle_sync_service()
    try:
        result = service.sync()
        return render_template(
            "moodle_integration.html",
            active_page="integrations",
            status=service.status(),
            preview=result.get("preview"),
            sync_result=result,
            error_message="",
        )
    except MoodleSyncError as error:
        return (
            render_template(
                "moodle_integration.html",
                active_page="integrations",
                status=service.status(),
                preview=None,
                sync_result=None,
                error_message=str(error),
            ),
            400,
        )


@web_blueprint.get("/notes")
def notes():
    """Render the operational Notes workspace."""
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


@web_blueprint.post("/obsidian/note/alex-handoff")
def obsidian_alex_handoff():
    """Build a local ZIP for manual handoff to Alex/ChatGPT; no upload is performed."""
    try:
        bundle = _alex_handoff_service().build_note_bundle(
            request.form.get("path", ""),
            include_full_vault=request.form.get("include_full_vault") == "1",
        )
        return send_file(
            BytesIO(bundle["payload"]),
            mimetype="application/zip",
            as_attachment=True,
            download_name=bundle["filename"],
            max_age=0,
        )
    except AlexHandoffError as error:
        return _render_obsidian_note_error(str(error), 400)
    except Exception as error:
        current_app.logger.warning(
            "Alex handoff unavailable (%s).",
            type(error).__name__,
        )
        return _render_obsidian_note_error(
            "The Alex handoff could not be prepared. Your vault was not changed.",
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
        return _companion_redirect(relative_path, saved_label)
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
        return _companion_redirect(relative_path, "archived")
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
