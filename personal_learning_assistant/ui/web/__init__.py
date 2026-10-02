"""Local web interface foundation for the Personal AI Learning Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import os

from flask import Flask

from .errors import register_error_handlers
from .routes import web_blueprint


def create_app(config: Mapping[str, Any] | None = None) -> Flask:
    """Create the local-only Flask application without loading academic engines."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_mapping(
        TESTING=False,
        JSON_SORT_KEYS=False,
        ASSESSMENT_COLAB_URL=os.environ.get("ANVAYA_COLAB_URL", ""),
        ASSESSMENT_CODING_HELPER_ENABLED=os.environ.get("ANVAYA_CODING_HELPER_ENABLED", "true").lower() == "true",
        ASSESSMENT_CODING_HELPER_EXAM_POLICY=os.environ.get("ANVAYA_CODING_HELPER_EXAM_POLICY", "disabled"),
    )
    if config:
        app.config.update(config)

    app.register_blueprint(web_blueprint)
    from .assessment_tools import assessment_tools_blueprint
    app.register_blueprint(assessment_tools_blueprint)
    register_error_handlers(app)
    return app
