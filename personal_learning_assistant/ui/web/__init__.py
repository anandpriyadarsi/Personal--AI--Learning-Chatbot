"""Local web interface foundation for the Personal AI Learning Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
    )
    if config:
        app.config.update(config)

    app.register_blueprint(web_blueprint)
    register_error_handlers(app)
    return app
