"""Local original-file manager. All writes explicit and same-origin protected."""
from __future__ import annotations
from functools import wraps
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
import hmac
import sqlite3
from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file, url_for
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary, LibraryError, MAX_UPLOAD
from personal_learning_assistant.services.native_document_extraction import ocr_available

files = Blueprint('native_library', __name__)
_creation_lock = Lock()
STATUS = {'stored':'Stored — waiting to index', 'indexing':'Indexing', 'ready':'Search Ready',
          'partial':'Partly searchable — OCR optional', 'ocr_required':'Scanned / blank PDF — OCR Required',
          'conversion_required':'Legacy PPT — Conversion Required', 'failed':'Indexing Failed — Retry',
          'unavailable':'Search Unavailable', 'disabled':'Content indexing off'}


def service():
    with _creation_lock:
        supplied = current_app.config.get('NATIVE_LIBRARY_SERVICE')
        if supplied is not None: return supplied
        if 'native_document_library' not in current_app.extensions:
            import config
            root = current_app.config.get('NATIVE_LIBRARY_ROOT') or Path(config.DATA_PATH)/'native_library'
            current_app.extensions['native_document_library'] = NativeDocumentLibrary(root)
        return current_app.extensions['native_document_library']


def catalogue():
    factory = current_app.config.get('NATIVE_LIBRARY_CATALOGUE_FACTORY')
    if factory: return factory()
    from personal_learning_assistant.learning_studio.sources import catalogue as read
    return read()


def subject(value, *, existing=None):
    value = value or None
    if value and value != existing and value not in {c['id'] for c in catalogue().get('courses',[])}:
        raise LibraryError('Choose an existing subject or leave the document unmapped.')
    return value


def protect(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_app.config.get('LEARNING_LIBRARY_ENABLED',True): abort(404)
        request.max_content_length = MAX_UPLOAD+1024*1024 if request.endpoint.endswith('.upload') else 32_000
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('Origin')
            expected=current_app.extensions['native_library_csrf']
            actual=request.headers.get('X-Library-CSRF','')
            if (not hmac.compare_digest(expected,actual) or
                (origin and origin.rstrip('/')!=request.host_url.rstrip('/')) or
                request.headers.get('Sec-Fetch-Site')=='cross-site'):
                return jsonify(error='Reload Library and retry this local action.'),403
        try:
            if any(len(request.args.getlist(k))>1 for k in request.args): raise LibraryError('Repeated filters are unsupported.')
            return fn(*args, **kwargs)
        except LibraryError as error: return jsonify(error=str(error)),error.status
        except (ValueError,TypeError): return jsonify(error='Choose valid Library fields and filters.'),400
        except (sqlite3.Error,OSError): return jsonify(error='Library storage is unavailable. Originals have not been intentionally modified.'),503
    return wrapped


def payload(allowed):
    data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-set(allowed): raise LibraryError('Supply valid action fields.')
    return data


def view_document(doc):
    return {**doc,'status_label':STATUS[doc['status']],
        'open_url':url_for('native_library.open_document',document_id=doc['id']),
        'download_url':url_for('native_library.original',document_id=doc['id'],download=1)}


@files.after_request
def private(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    return response


@files.get('/library/files')
@protect
def home():
    lib=service(); folder=request.args.get('folder_id') or None
    folders=lib.folders(); by_id={f['id']:f for f in folders}
    crumbs=[]; current=folder
    while current and len(crumbs)<100:
        if current not in by_id: raise LibraryError('Folder not found.',404)
        crumbs.insert(0,by_id[current]); current=by_id[current]['parent_id']
    query=request.args.get('q',''); course=request.args.get('subject_id') or None
    page=lib.list_documents(folder_id=folder,subject_id=course,sort=request.args.get('sort','newest'),
                            kind=request.args.get('kind') or None,page=request.args.get('page',1))
    matches=lib.search(query,folder_id=folder,subject_id=course,offset=int(request.args.get('offset',0)),limit=50) if query else []
    return render_template('native_library.html',active_page='library', page=page,
        documents=[view_document(d) for d in page['items']], folders=folders,
        child_folders=[f for f in folders if f['parent_id']==folder], crumbs=crumbs, folder_id=folder,
        courses=catalogue().get('courses',[]), query=query, matches=matches, status_labels=STATUS,
        csrf_token=current_app.extensions['native_library_csrf'], ocr_available=ocr_available())


@files.post('/library/files/upload')
@protect
def upload():
    for field in ('subject_id','folder_id','indexing'):
        if len(request.form.getlist(field))>1: raise LibraryError('Repeated upload fields are unsupported.')
    if len(request.files.getlist('file'))!=1: raise LibraryError('Choose one original document per upload.')
    file=request.files['file']
    doc=service().upload(file.stream,file.filename,folder_id=request.form.get('folder_id') or None,
        subject_id=subject(request.form.get('subject_id')),indexing=request.form.get('indexing','true')!='false')
    return jsonify(document=view_document(doc)),201


@files.get('/library/files/search')
@protect
def search():
    matches=service().search(request.args.get('q',''),folder_id=request.args.get('folder_id') or None,
        subject_id=request.args.get('subject_id') or None,document_id=request.args.get('document_id') or None,
        offset=int(request.args.get('offset',0)),limit=int(request.args.get('limit',50)))
    return jsonify(matches=[{**view_document(d),'open_url':url_for('native_library.open_document',document_id=d['id'],position=d['position'] or 1,q=request.args.get('q',''))} for d in matches])


@files.get('/library/files/status')
@protect
def status():
    identities=request.args.get('ids','').split(',')
    if len(identities)>30: raise LibraryError('Status is limited to the visible page.')
    return jsonify(documents=[view_document(service().get(identity)) for identity in identities if identity])


@files.route('/library/files/<document_id>',methods=['GET','PATCH','DELETE'])
@protect
def document(document_id):
    lib=service()
    if request.method=='GET':
        d=view_document(lib.get(document_id))
        # Explicit details only; never place machine paths or capabilities in links.
        d['storage_location']='On this ANVAYA device/host: '+str(lib.root/'blobs'/d['sha256'])
        return jsonify(document=d)
    if request.method=='DELETE':
        if payload({'confirm'}).get('confirm') is not True: raise LibraryError('Confirm permanent document deletion.')
        lib.delete(document_id); return jsonify(deleted=True)
    data=payload({'display_name','folder_id','subject_id','topic','tags'})
    if 'subject_id' in data: data['subject_id']=subject(data['subject_id'],existing=lib.get(document_id)['subject_id'])
    return jsonify(document=view_document(lib.update(document_id,**data)))


@files.post('/library/files/<document_id>/copy')
@protect
def copy(document_id):
    payload(set())
    return jsonify(document=view_document(service().copy(document_id))),201


@files.post('/library/files/<document_id>/index')
@protect
def index(document_id):
    data=payload({'enabled','ocr','rebuild'})
    if 'enabled' in data: service().set_indexing(document_id,data['enabled'])
    elif data.get('rebuild') is True:
        if data.get('ocr') not in (True,False,None): raise LibraryError('OCR must be a boolean.')
        if data.get('ocr') and not ocr_available(): raise LibraryError('Optional local OCR is unavailable on this device.',409)
        service().rebuild(document_id,ocr=bool(data.get('ocr')))
    else: raise LibraryError('Choose enable, disable or rebuild indexing.')
    return jsonify(document=view_document(service().get(document_id)))


@files.post('/library/files/rebuild')
@protect
def rebuild():
    payload(set()); service().rebuild()
    return jsonify(queued=True)


@files.post('/library/files/folders')
@protect
def folder_create():
    data=payload({'name','parent_id'})
    return jsonify(service().create_folder(data.get('name'),data.get('parent_id') or None)),201


@files.route('/library/files/folders/<folder_id>',methods=['PATCH','DELETE'])
@protect
def folder_update(folder_id):
    data=payload({'name','parent_id','confirm'})
    if request.method=='DELETE':
        if data.get('confirm') is not True: raise LibraryError('Confirm folder deletion.')
        service().delete_folder(folder_id)
    else: service().update_folder(folder_id,data.get('name'),data.get('parent_id') or None)
    return jsonify(saved=True)


@files.get('/library/files/<document_id>/original')
@protect
def original(document_id):
    d=service().get(document_id)
    response=send_file(service().original(document_id),mimetype=d['mime'],
        as_attachment=request.args.get('download')=='1', download_name=d['original_name'],conditional=True)
    response.headers['Content-Security-Policy']='sandbox'
    return response


@files.get('/library/files/<document_id>/open')
@protect
def open_document(document_id):
    d=view_document(service().get(document_id))
    position=int(request.args.get('position',1))
    if not 1<=position<=2500: raise LibraryError('Choose a valid page or slide.')
    query=request.args.get('q','')
    if len(query)>500: raise LibraryError('Search is limited to 500 characters.')
    return render_template('native_document.html',active_page='library',doc=d,position=position,query=query,
        csrf_token=current_app.extensions['native_library_csrf'])


@files.get('/library/files/<document_id>/preview/<int:position>.png')
@protect
def preview(document_id,position):
    # Optional desktop page rendering; an original is never replaced by a preview.
    d=service().get(document_id)
    if d['kind']!='pdf': raise LibraryError('Use a compatible slide viewer.',409)
    try: import fitz
    except ImportError: raise LibraryError('Page preview unavailable; open the original in a PDF viewer.',409)
    if not 1<=position<=2500: raise LibraryError('Invalid page.')
    from io import BytesIO
    with fitz.open(service().original(document_id)) as pdf:
        if pdf.is_encrypted or position>len(pdf): raise LibraryError('Page unavailable.',404)
        p=pdf[position-1]
        query=request.args.get('q','')
        if len(query)>500: raise LibraryError('Search is limited to 500 characters.')
        if query.strip():
            for rectangle in p.search_for(query.strip('"'))[:100]: p.add_highlight_annot(rectangle)
        scale=min(2.0,1800/max(p.rect.width,p.rect.height))
        raw=p.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png')
    return send_file(BytesIO(raw),mimetype='image/png')


@files.get('/library/files/<document_id>/learning')
@protect
def learning(document_id):
    return render_template('native_learning_handoff.html',active_page='library',doc=view_document(service().get(document_id)))


def register_native_library(app):
    app.extensions['native_library_csrf']=token_urlsafe(32)
    app.register_blueprint(files)
