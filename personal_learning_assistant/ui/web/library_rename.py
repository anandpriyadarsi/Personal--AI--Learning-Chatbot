"""Explicit same-origin metadata write, separate from read-only Library GETs."""
import hmac
from secrets import token_urlsafe
from flask import Blueprint, current_app, jsonify, request


def register_library_rename(app):
    app.extensions['library_rename_csrf'] = token_urlsafe(32)

    @app.context_processor
    def context():
        return {'library_rename_csrf':app.extensions['library_rename_csrf']}

    bp = Blueprint('library_rename',__name__)

    @bp.post('/library/items/<kind>/<item_id>/rename')
    def rename(kind,item_id):
        from .routes import _learning_library_service
        from personal_learning_assistant.repositories.sqlite.learning_library_repository import (
            LibraryNotFoundError, LibraryUnavailableError)
        if current_app.config.get('LEARNING_LIBRARY_ENABLED',True) is not True:
            return jsonify(error='Library is unavailable.'),404
        token = request.headers.get('X-Library-CSRF','')
        if (not hmac.compare_digest(token,app.extensions['library_rename_csrf']) or
                request.headers.get('Sec-Fetch-Site') == 'cross-site' or
                (request.headers.get('Origin') and request.headers['Origin'].rstrip('/') != request.host_url.rstrip('/'))):
            return jsonify(error='Reload the Library and try again.'),403
        request.max_content_length = 4096
        data = request.get_json(silent=True)
        if (not isinstance(data,dict) or set(data) != {'title','expected_title'} or
                not isinstance(data['expected_title'],str) or len(data['expected_title']) > 2048):
            return jsonify(error='Enter a valid document name.'),400
        try:
            result = _learning_library_service().rename(kind,item_id,data['title'],
                expected_title=data['expected_title'])
            return jsonify(result)
        except ValueError as error:
            return jsonify(error=str(error)),409 if 'changed' in str(error) else 400
        except LibraryNotFoundError:
            return jsonify(error='Material was not found.'),404
        except LibraryUnavailableError:
            return jsonify(error='Library names are temporarily unavailable. Try again.'),503

    @bp.after_request
    def private(response):
        response.headers['Cache-Control']='no-store'
        return response

    app.register_blueprint(bp)
