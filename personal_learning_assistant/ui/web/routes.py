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
from personal_learning_assistant.services.planning_dashboard_service import (
    load_planning_dashboard,
    unavailable_planning_dashboard,
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


def _academic_agent_service():
    factory = (
        current_app.config.get("ACADEMIC_AGENT_WEB_SERVICE_FACTORY")
        or build_academic_agent_web_service
    )
    return factory()


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
    """Render the read-only academic Home dashboard."""
    return render_template(
        "home.html",
        active_page="home",
        dashboard=_home_dashboard(),
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
    """Render the read-only Progress & Planning workspace."""
    return render_template("planning.html", active_page="planning", dashboard=_planning_dashboard())


@web_blueprint.get("/calendar")
def calendar():
    """Render the read-only Calendar & Grades workspace."""
    return render_template("calendar.html", active_page="calendar", dashboard=_calendar_grades_dashboard())


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
    """Preview one current Markdown note without mutating the vault."""
    service = _obsidian_workspace_service()
    try:
        note = service.note_preview(request.args.get("path", "", type=str))
        return render_template(
            "obsidian_note.html",
            active_page="obsidian",
            note=note,
            error_message="",
        )
    except ObsidianWorkspaceValidationError:
        return (
            render_template(
                "obsidian_note.html",
                active_page="obsidian",
                note=None,
                error_message="Choose a valid Markdown note inside the configured vault.",
            ),
            400,
        )
    except ObsidianWorkspaceNotFoundError:
        return (
            render_template(
                "obsidian_note.html",
                active_page="obsidian",
                note=None,
                error_message="That Markdown note was not found in the current vault.",
            ),
            404,
        )
    except ObsidianWorkspaceUnavailableError:
        return (
            render_template(
                "obsidian_note.html",
                active_page="obsidian",
                note=None,
                error_message="The note changed or could not be read safely. Refresh the Obsidian workspace and try again.",
            ),
            503,
        )


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
    """Render read-only Phase 5.8 retrieval evidence and RAG context."""
    query = request.args.get("q", "", type=str)
    return render_template("knowledge.html", active_page="knowledge", dashboard=_knowledge_dashboard(query))


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
