"""Optional Obsidian connections under Library, with explicit copy actions."""
import hmac
import io
from functools import wraps
from secrets import token_urlsafe

from flask import Blueprint, current_app, redirect, render_template, request, url_for, has_request_context, send_file, abort
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
    _service().import_snapshot(item.stream.read(MAX_ARCHIVE_BYTES + 1), refresh=request.form.get("connection_action") == "refresh")
    return redirect(url_for("web.obsidian", snapshot="1"), code=303)


@connections.post("/connect")
@_action
def connect():
    if current_app.config.get("PRIVATE_MOBILE_MODE"):
        return _render("Use a ZIP snapshot on Android. Desktop folder paths are unavailable here.", 400)
    _service().connect_folder(request.form.get("vault_path"))
    return redirect(url_for("web.obsidian", connected="1"), code=303)


@connections.post('/relocate')
@_action
def relocate_folder():
    if current_app.config.get('PRIVATE_MOBILE_MODE'):
        return _render('Folder relocation is only available on the local host.', 400)
    _service().workspace.relocate_connection(request.form.get('vault_path'), expected_connection_id=request.form.get('connection_id'))
    return redirect(url_for('obsidian_connections.settings'), code=303)


@connections.post("/disconnect")
@_action
def disconnect():
    _service().disconnect()
    return redirect(url_for("obsidian_connections.settings", disconnected="1"), code=303)


@connections.post("/import")
@_action
def copy_notes():
    paths = request.form.getlist("paths")
    expected = {path: request.form.get("source_hash[" + path + "]") for path in paths if request.form.get("source_hash[" + path + "]")}
    copied = _service().copy_notes(paths, expected_versions=expected)
    return redirect(url_for("obsidian_connections.settings", copied=len(copied)), code=303)


@connections.post("/refresh")
@_action
def refresh_manifest():
    _service().workspace.refresh_manifest()
    return redirect(url_for("obsidian_connections.settings", refreshed="1"), code=303)


@connections.post("/rename")
@_action
def confirm_rename():
    _service().workspace.confirm_rename(request.form.get("old_path"), request.form.get("new_path"), expected_hash=request.form.get("source_hash"))
    return redirect(url_for("obsidian_connections.settings", refreshed="1"), code=303)


@connections.get("/asset")
def asset():
    try:
        payload = _service().workspace.read_asset(request.args.get("path"))
    except (ObsidianWorkspaceError, OSError, RuntimeError, ValueError):
        abort(404)
    response = send_file(io.BytesIO(payload["bytes"]), mimetype=payload["mimetype"], download_name="vault-image", max_age=0)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response


@connections.get("/export")
def export_markdown():
    try:
        note = _service().workspace.validate_note_version(request.args.get("path"), request.args.get("sha256") or "")
    except (ObsidianWorkspaceError, OSError, RuntimeError, ValueError):
        abort(409)
    # Byte-preserving download includes BOM/unknown frontmatter. Revalidation
    # above prevents exporting a different version after the reader was opened.
    reader = _service().workspace
    from personal_learning_assistant.repositories.filesystem.obsidian_workspace_reader import ObsidianWorkspaceReader
    config = reader._load_config()
    payload = ObsidianWorkspaceReader(config["vault_path"]).read_note(note["relative_path"], expected_hash=note["source_hash"])
    response = send_file(io.BytesIO(payload["bytes"]), mimetype="text/markdown", as_attachment=True, download_name=note["relative_path"].rsplit("/", 1)[-1], max_age=0)
    response.headers["X-ANVAYA-Exclusions"] = "Attachments; Obsidian plugins; companion history"
    return response


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
