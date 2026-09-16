"""Read-only routes for the local Personal AI Learning Assistant web UI."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template

from personal_learning_assistant.services.course_dashboard_service import (
    load_course_catalogue,
    unavailable_course_catalogue,
)
from personal_learning_assistant.services.home_dashboard_service import (
    load_home_dashboard,
    unavailable_home_dashboard,
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


@web_blueprint.get("/healthz")
def healthz():
    """Return a side-effect-free health response for local startup checks."""
    return jsonify(
        phase="7.5.1",
        service="personal-learning-assistant-web",
        status="ok",
    )
