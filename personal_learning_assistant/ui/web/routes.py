"""Read-only routes for the local Personal AI Learning Assistant web UI."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

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


@web_blueprint.get("/healthz")
def healthz():
    """Return a side-effect-free health response for local startup checks."""
    return jsonify(
        phase="7.5.1",
        service="personal-learning-assistant-web",
        status="ok",
    )
