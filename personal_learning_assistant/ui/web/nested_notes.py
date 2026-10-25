"""Lazy section reads and explicit conflict-checked note mutations."""
import hmac
from functools import wraps
from flask import Blueprint,current_app,jsonify,request
from personal_learning_assistant.repositories.json.anvaya_notes_repository import AnvayaNotesNotFoundError,AnvayaNotesConflictError,AnvayaNotesRepositoryError
from personal_learning_assistant.services.anvaya_notes_service import AnvayaNotesValidationError
from personal_learning_assistant.services.nested_notes_service import NestedNotesService

sections=Blueprint('nested_notes',__name__)

def errors(fn):
    @wraps(fn)
    def run(*args,**kw):
        try: return fn(*args,**kw)
        except AnvayaNotesNotFoundError: return jsonify(error='Note or section was not found.'),404
        except AnvayaNotesConflictError as e: return jsonify(error=str(e)),409
        except AnvayaNotesValidationError as e: return jsonify(error=str(e)),400
        except (OSError,AnvayaNotesRepositoryError): return jsonify(error='Notes could not be saved. Keep your draft and try again.'),503
    return run

def service():
    from .routes import _anvaya_notes_service
    return NestedNotesService(_anvaya_notes_service().repository)

@sections.route('/notes/sections/<note_id>',methods=['GET','POST'])
@errors
def collection(note_id):
    if request.method=='GET': return jsonify(service().list(note_id,request.args.get('q','')))
    if not hmac.compare_digest(request.headers.get('X-Notes-CSRF',''),current_app.extensions['notes_media_csrf']): return jsonify(error='Refresh the note before changing sections.'),403
    data=request.get_json(silent=True)
    if not isinstance(data,dict): return jsonify(error='A section request is required.'),400
    if not isinstance(data.get('expected_updated_at'),str) or not data['expected_updated_at']:
        return jsonify(error='A saved note version is required. Refresh before saving.'),400
    keys=('expected_updated_at','section_id','title','body','order','target_note_id','target_updated_at')
    return jsonify(service().change(note_id,data.get('action',''),**{k:data[k] for k in keys if k in data}))

@sections.get('/notes/sections/<note_id>/destinations')
@errors
def destinations(note_id):
    store=service().repository
    store.get_note(note_id)
    return jsonify(notes=[{'id':n['id'],'title':n['title'],'version':n['updated_at']} for n in store.list_notes() if n['id']!=note_id and n.get('status','active')=='active'])

@sections.get('/notes/sections/<note_id>/<section_id>')
@errors
def detail(note_id,section_id): return jsonify(service().read(note_id,section_id))

def register_nested_notes(app): app.register_blueprint(sections)
