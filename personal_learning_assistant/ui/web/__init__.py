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
        LEARNING_LIBRARY_ENABLED=os.environ.get("ANVAYA_LIBRARY_ENABLED", "true").strip().lower() == "true",
        LEARNING_LIBRARY_DATABASE_PATH=os.environ.get("ANVAYA_LIBRARY_DATABASE_PATH") or None,
        ACADEMIC_EVIDENCE_ENABLED=os.environ.get('ANVAYA_EVIDENCE_ENABLED','true').strip().lower()=='true',
        JSON_SORT_KEYS=False,
        ASSESSMENT_COLAB_URL=os.environ.get("ANVAYA_COLAB_URL", ""),
        ASSESSMENT_CODING_HELPER_ENABLED=os.environ.get("ANVAYA_CODING_HELPER_ENABLED", "true").lower() == "true",
        ASSESSMENT_CODING_HELPER_EXAM_POLICY=os.environ.get("ANVAYA_CODING_HELPER_EXAM_POLICY", "disabled"),
        ASSESSMENT_EXTENDED_ENABLED=os.environ.get("ANVAYA_ASSESSMENT_EXTENDED", "false").strip().lower() == "true",
    )
    if config:
        app.config.update(config)

    from .tutor_rendering import render_tutor_markdown
    app.jinja_env.filters["tutor_markdown"] = render_tutor_markdown

    # Process-local key: short-lived helper context becomes invalid on restart.
    from secrets import token_bytes
    from personal_learning_assistant.services.coding_helper_context import context_signer
    app.extensions["coding_helper_signer"] = context_signer(token_bytes(32))
    app.register_blueprint(web_blueprint)
    from .assessment_tools import assessment_tools_blueprint
    app.register_blueprint(assessment_tools_blueprint)
    from secrets import token_urlsafe
    app.extensions['learning_studio_csrf'] = token_urlsafe(32)
    app.extensions['tutor_action_csrf'] = token_urlsafe(32)

    @app.context_processor
    def _tutor_action_context():
        # Never expose an application secret as a reusable browser CSRF token.
        # This is a process-local random token for explicit local-only actions.
        return {"tutor_action_csrf": app.extensions["tutor_action_csrf"]}
    from .learning_studio import learning_blueprint
    app.register_blueprint(learning_blueprint)
    if app.config.get("ASSESSMENT_EXTENDED_ENABLED") is True:
        import config as installed_config
        from secrets import token_bytes
        from personal_learning_assistant.services.assessment_execution_service import AssessmentExecutionService
        from .assessment_execution_candidate import create_production_blueprint

        def extended_service():
            configured = app.config.get("ASSESSMENT_EXTENDED_SERVICE_FACTORY")
            return (configured() if callable(configured)
                    else AssessmentExecutionService(installed_config.DATABASE_PATH, production=True))

        app.register_blueprint(create_production_blueprint(
            extended_service, secret_key=token_bytes(32)
        ))
    from .planning_approval_controls import register_approval_controls
    register_approval_controls(app)
    from .planning_proposals import register_planning_proposals
    from .routes import _operational_planner_service
    register_planning_proposals(app, _operational_planner_service)
    from .academic_evidence import register_academic_evidence
    register_academic_evidence(app)
    register_error_handlers(app)
    return app
