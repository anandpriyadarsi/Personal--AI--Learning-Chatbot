"""Read-only routes for the Phase 7.5.1 web foundation."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template


web_blueprint = Blueprint("web", __name__)


@web_blueprint.get("/")
def home():
    """Render the local application shell without touching academic data."""
    return render_template("home.html", active_page="home")


@web_blueprint.get("/healthz")
def healthz():
    """Return a side-effect-free health response for local startup checks."""
    return jsonify(
        phase="7.5.1",
        service="personal-learning-assistant-web",
        status="ok",
    )
