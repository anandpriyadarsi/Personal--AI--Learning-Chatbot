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
    """Render the read-only Notes library."""
    return render_template("notes.html", active_page="notes", dashboard=_notes_dashboard())


@web_blueprint.get("/resources")
def resources():
    """Render the read-only Resources library."""
    return render_template("resources.html", active_page="resources", dashboard=_resources_dashboard())


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
