"""Optional Obsidian connections under Library, with explicit copy actions."""
import hmac
from functools import wraps
from secrets import token_urlsafe

from flask import Blueprint, current_app, redirect, render_template, request, url_for, has_request_context
from werkzeug.exceptions import RequestEntityTooLarge

from personal_learning_assistant.services.obsidian_connection_service import (
    MAX_ARCHIVE_BYTES, build_obsidian_connection_service,
)
from personal_learning_assistant.services.obsidian_workspace_service import (
    ObsidianWorkspaceError, ObsidianWorkspaceValidationError,
)
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesError

connections = Blueprint("obsidian_connections", __name__, url_prefix="/library/connected-sources/obsidian")


def _service():
    factory = current_app.config.get("OBSIDIAN_CONNECTION_SERVICE_FACTORY")
    if callable(factory):
        return factory()
    from .routes import _obsidian_workspace_service, _anvaya_notes_service
    return build_obsidian_connection_service(_obsidian_workspace_service(), _anvaya_notes_service())


def _render(message="", status=200):
    return render_template("obsidian_connection.html", active_page="library",
                           connection=_service().status(), error_message=message), status


def _action(fn):
    @wraps(fn)
    def run(*args, **kwargs):
        try:
            request.max_content_length = MAX_ARCHIVE_BYTES + 1024 * 1024
            supplied = str(request.headers.get("X-Notes-CSRF") or request.form.get("csrf_token") or "")
            expected = str(current_app.extensions.get("notes_media_csrf") or "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return _render("Refresh this page before changing your Obsidian connection.", 403)
            return fn(*args, **kwargs)
        except ObsidianWorkspaceValidationError as error:
            return _render(str(error), 400)
        except RequestEntityTooLarge:
            return _render("Choose a vault ZIP snapshot of 25 MB or smaller.", 413)
        except (ObsidianWorkspaceError, AnvayaNotesError, OSError):
            return _render("The action could not finish. Check storage and refresh before trying again. Existing source files were not changed.", 503)
    return run


@connections.get("")
def settings():
    return _render()


@connections.post("/snapshot")
@_action
def snapshot():
    item = request.files.get("snapshot")
    if item is None or not str(item.filename or "").lower().endswith(".zip"):
        return _render("Choose a .zip vault snapshot.", 400)
    _service().import_snapshot(item.stream.read(MAX_ARCHIVE_BYTES + 1))
    return redirect(url_for("web.obsidian", snapshot="1"), code=303)


@connections.post("/connect")
@_action
def connect():
    if current_app.config.get("PRIVATE_MOBILE_MODE"):
        return _render("Use a ZIP snapshot on Android. Desktop folder paths are unavailable here.", 400)
    _service().connect_folder(request.form.get("vault_path"))
    return redirect(url_for("web.obsidian", connected="1"), code=303)


@connections.post("/disconnect")
@_action
def disconnect():
    _service().disconnect()
    return redirect(url_for("obsidian_connections.settings", disconnected="1"), code=303)


@connections.post("/import")
@_action
def copy_notes():
    copied = _service().copy_notes(request.form.getlist("paths"))
    return redirect(url_for("obsidian_connections.settings", copied=len(copied)), code=303)


def register_obsidian_connections(app):
    app.extensions.setdefault("notes_media_csrf", token_urlsafe(32))
    app.register_blueprint(connections)

    @app.context_processor
    def connection_context():
        context = {"notes_media_csrf": app.extensions["notes_media_csrf"]}
        if has_request_context() and request.endpoint in {"web.obsidian", "web.obsidian_note"}:
            try:
                context["obsidian_connection"] = _service().status()
            except (OSError, ObsidianWorkspaceError):
                context["obsidian_connection"] = {"mode": "folder", "state": "Unavailable"}
        return context

    @app.after_request
    def connection_headers(response):
        if request.blueprint == "obsidian_connections":
            response.headers["Cache-Control"] = "no-store"
        return response
