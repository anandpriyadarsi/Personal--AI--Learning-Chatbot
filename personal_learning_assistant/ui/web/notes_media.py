"""Lazy note-media endpoints. Browser file actions always download, never embed."""
import hmac
from functools import wraps
from secrets import token_urlsafe

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from personal_learning_assistant.services.notes_media_service import (
    NotesMediaStore, MAX_MEDIA_REQUEST_BYTES, AnvayaNotesValidationError,
    AnvayaNotesUnavailableError, AnvayaNotesNotFoundError,
)

media = Blueprint('notes_media', __name__)


def _store():
    from .routes import _anvaya_notes_service
    return NotesMediaStore(_anvaya_notes_service().repository)


def _errors(fn):
    @wraps(fn)
    def handle(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AnvayaNotesNotFoundError:
            return jsonify(error='Attachment or handwritten note not found. Refresh the note.'),404
        except AnvayaNotesValidationError as error:
            return jsonify(error=str(error)),400
        except (AnvayaNotesUnavailableError, OSError):
            return jsonify(error='Attachment unavailable. Check storage or attach the original file again.'),503
        except RequestEntityTooLarge:
            return jsonify(error='The upload is too large. Use files under 512 MB, with a batch under 1 GB.'),413
    return handle


def _csrf():
    value = request.headers.get('X-Notes-CSRF','')
    return hmac.compare_digest(value,current_app.extensions['notes_media_csrf'])


@media.route('/notes/media/<note_id>', methods=['GET','POST'])
@_errors
def attachments(note_id):
    if request.method=='GET':
        return jsonify(attachments=_store().list(note_id))
    # This endpoint alone admits large streamed media. Other academic forms keep
    # their existing limits. Set this before Werkzeug parses the multipart body.
    request.max_content_length = MAX_MEDIA_REQUEST_BYTES + 1024*1024
    if not _csrf():
        return jsonify(error='Refresh the note before attaching media.'),403
    files = request.files.getlist('files')
    items = _store().add(note_id,[(item.filename,item.stream) for item in files])
    return jsonify(attachments=items),201


@media.post('/notes/media/<note_id>/<asset_id>/<action>')
@_errors
def change(note_id, asset_id, action):
    if not _csrf():
        return jsonify(error='Refresh the note before changing attachments.'),403
    if action=='rename':
        payload = request.get_json(silent=True) or {}
        return jsonify(attachment=_store().rename(note_id,asset_id,payload.get('filename')))
    if action=='delete':
        _store().delete(note_id,asset_id)
        return jsonify(deleted=True)
    return jsonify(error='Unknown attachment action.'),404


@media.get('/notes/media/<note_id>/<asset_id>/<action>')
@_errors
def file_action(note_id, asset_id, action):
    if action not in ('file','open','share'):
        return jsonify(error='Unknown attachment action.'),404
    item = _store().resolve(note_id,asset_id)
    response = send_file(item['path'],mimetype=item['mimetype'],as_attachment=True,
                         download_name=item['filename'],conditional=True,etag=item['sha256'])
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'none'; sandbox"
    return response


def register_notes_media(app):
    app.extensions['notes_media_csrf']=token_urlsafe(32)
    app.register_blueprint(media)

    @app.context_processor
    def media_context():
        return {'notes_media_csrf':app.extensions['notes_media_csrf']}

    @app.after_request
    def media_headers(response):
        if request.blueprint=='notes_media':
            response.headers['Cache-Control']='no-store'
        return response
