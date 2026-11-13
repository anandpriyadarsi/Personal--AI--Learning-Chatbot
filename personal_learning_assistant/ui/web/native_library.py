"""Local original-file manager. All writes explicit and same-origin protected."""
from __future__ import annotations
from collections import OrderedDict
from functools import wraps
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
import hmac
import re
import sqlite3
from flask import Blueprint, abort, current_app, jsonify, render_template, request, send_file, url_for
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary, LibraryError, MAX_UPLOAD, document_filename
from personal_learning_assistant.services.native_document_extraction import ocr_available

files = Blueprint('native_library', __name__)
_creation_lock = Lock()
TUTOR_STATUS={'partly_readable':'Partly readable · Ready for Tutor','ready':'Ready for Tutor','preparing':'Preparing for Tutor','stored_only':'Stored only','disabled':'Saved · Tutor processing off','attention':'Needs attention'}
STATUS = {'stored':'Stored — waiting to index', 'indexing':'Indexing', 'ready':'Search Ready',
          'partial':'Partly searchable — OCR optional', 'ocr_required':'Scanned / blank PDF — OCR Required',
          'conversion_required':'Legacy PPT — Conversion Required', 'failed':'Indexing Failed — Retry',
          'unavailable':'Search Unavailable', 'disabled':'Content indexing off'}


def service():
    with _creation_lock:
        supplied = current_app.config.get('NATIVE_LIBRARY_SERVICE')
        if supplied is not None: return supplied
        if 'native_document_library' not in current_app.extensions:
            if not current_app.config.get('ANDROID_LOCAL_RUNTIME'):
                raise LibraryError('Start the local website with python phase7_web.py to prepare Library safely.',503)
            initialize_library(current_app._get_current_object())
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
        request.max_content_length = MAX_UPLOAD+1024*1024 if request.endpoint.endswith(('.upload','.repair')) else 32_000
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
    if doc.get('status')=='partial' and doc.get('tutor_state')=='ready':
        doc=dict(doc);doc['tutor_state']='partly_readable'
    return {**{k:v for k,v in doc.items() if k!='managed_original'},'status_label':TUTOR_STATUS.get(doc.get('tutor_state'),STATUS.get(doc['status'],'Saved')), 'filename':document_filename(doc),
        'open_url':url_for('native_library.original',document_id=doc['id'],native_action='view'),
        'open_with_url':url_for('native_library.original',document_id=doc['id'],native_action='open_with'),
        'share_url':url_for('native_library.original',document_id=doc['id'],native_action='share'),
        'reader_url':url_for('native_library.open_document',document_id=doc['id'],native_action='reader'),
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
    courses=catalogue().get('courses',[])
    crumbs=lib.breadcrumbs(folder) if folder else []
    children=lib.children(folder,offset=int(request.args.get('folder_offset',0)))
    folders=children['items']
    query=request.args.get('q',''); course=request.args.get('subject_id') or None
    view=request.args.get('collection')
    page=lib.collection(view,offset=int(request.args.get('offset',0))) if view else lib.list_documents(folder_id=folder,subject_id=course,sort=request.args.get('sort','newest'),
                            kind=request.args.get('kind') or None,page=request.args.get('page',1))
    content=request.args.get('content')=='1'
    searcher=lib.search if content else lib.metadata_search
    matches=searcher(query,kind=request.args.get('kind') or None,folder_id=None if request.args.get('scope')=='all' else folder,subject_id=course,offset=int(request.args.get('offset',0)),limit=50) if query else []
    return render_template('native_library.html',active_page='library', page=page,
        documents=[view_document(d) for d in page['items']], folders=folders,
        child_folders=folders if not view else [], crumbs=crumbs, folder_id=folder,
        child_page=children,collection=view,usage=lib.storage_usage(),semesters=lib.semesters(),
        courses=catalogue().get('courses',[]), query=query, matches=[view_document(d) for d in matches], status_labels=STATUS,
        csrf_token=current_app.extensions['native_library_csrf'], ocr_available=ocr_available())


@files.post('/library/files/upload')
@protect
def upload():
    for field in ('subject_id','folder_id','indexing','duplicate'):
        if len(request.form.getlist(field))>1: raise LibraryError('Repeated upload fields are unsupported.')
    if len(request.files.getlist('file'))!=1: raise LibraryError('Choose one original document per upload.')
    file=request.files['file']
    doc=service().upload(file.stream,file.filename,folder_id=request.form.get('folder_id') or None,
        subject_id=subject(request.form.get('subject_id')),indexing=request.form.get('indexing','false')=='true',duplicate=request.form.get('duplicate') or None)
    return jsonify(document=view_document(doc)),201


@files.get('/library/files/search')
@protect
def search():
    matches=service().search(request.args.get('q',''),folder_id=request.args.get('folder_id') or None,
        subject_id=request.args.get('subject_id') or None,document_id=request.args.get('document_id') or None,
        offset=int(request.args.get('offset',0)),limit=int(request.args.get('limit',50)))
    return jsonify(matches=[{**view_document(d),'open_url':url_for('native_library.open_document',document_id=d['id'],position=d['position'] or 1)} for d in matches])


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
        d['storage_location']='Private storage on this device'
        with lib.connection() as con:
            d['linked_sources']=con.execute('SELECT count(*) FROM source_links WHERE document_id=?',(document_id,)).fetchone()[0]
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
    data=payload({'folder_id'})
    lib=service()
    copied=lib.copy(document_id,folder_id=data['folder_id']) if 'folder_id' in data else lib.copy(document_id)
    return jsonify(document=view_document(copied)),201


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
    data=payload({'name','parent_id','confirm','confirm_scope','sort_order'})
    if request.method=='DELETE':
        if data.get('confirm') is not True: raise LibraryError('Confirm folder deletion.')
        service().delete_folder(folder_id)
    else: service().update_folder(folder_id,data.get('name'),data.get('parent_id') or None,confirm_scope=data.get('confirm_scope') is True,sort_order=data.get('sort_order'))
    return jsonify(saved=True)


@files.get('/library/files/<document_id>/original')
@protect
def original(document_id):
    d=service().get(document_id)
    service().mark_opened(document_id)
    response=send_file(service().original(document_id),mimetype=d['mime'],
        as_attachment=request.args.get('download')=='1', download_name=document_filename(d),conditional=True)
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
    text_preview=None
    if d['kind'] in ('txt','md','csv','py'):
        with service().original(document_id).open('rb') as stream:
            text_preview=stream.read(256_001)
        text_preview=text_preview[:256_000].decode('utf-8',errors='replace') + ('\n[Preview limited to 256 KB. Download original for the full file.]' if len(text_preview)>256_000 else '')
    transcript_cues=[]
    if d['kind'] in ('srt','vtt'):
        from personal_learning_assistant.ingestion.extractors import TranscriptExtractor
        transcript_cues=TranscriptExtractor().extract(service().original(document_id).read_bytes(),source_name=d['filename'])
    return render_template('native_document.html' ,active_page='library',doc=d,position=position,query=query,text_preview=text_preview,
        csrf_token=current_app.extensions['native_library_csrf'],transcript_cues=transcript_cues,
        frame_options=[x for x in service().list_documents()['items'] if x['kind'] in ('png','jpg','jpeg','webp') and x['subject_id']==d['subject_id']])


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
    lib=service();doc=view_document(lib.get(document_id))
    if doc['kind']=='pdf' and doc['size']<=20*1024*1024:
        with lib.connection() as con:
            linked=con.execute("SELECT source_id FROM source_links WHERE document_id=? AND namespace='canonical' AND content_hash=?",(document_id,doc['sha256'])).fetchone()
        if linked:doc['canonical_source_id']=linked['source_id']
    return render_template('native_learning_handoff.html',active_page='library',doc=doc)


@files.get('/library/files/<document_id>/thumbnail.png')
@protect
def thumbnail(document_id):
    """Small, local first-page render; no conversion during the folder GET.

    The per-app LRU holds at most 64 PNGs in RAM, keyed by original hash so
    copies share a render. Responses remain no-store and nothing is published.
    """
    lib = service()
    doc = lib.get(document_id)
    if doc['kind'] != 'pdf':
        raise LibraryError('Slide preview unavailable; use the file-type icon.', 409)
    # Recheck existence and integrity even for a cached render, including copies.
    original_path = lib.original(document_id)
    try:
        import fitz
    except ImportError:
        raise LibraryError('PDF preview unavailable; use the file-type icon.', 409)
    from io import BytesIO
    cache = current_app.extensions['native_library_thumbnails']
    # Serialize small renders: PyMuPDF must not render concurrently here.
    with cache['lock']:
        images = cache['images']
        raw = images.get(doc['sha256'])
        if raw is None:
            try:
                with fitz.open(original_path) as pdf:
                    if pdf.is_encrypted or not len(pdf):
                        raise LibraryError('First page unavailable; use the file-type icon.', 409)
                    page = pdf[0]
                    extent = max(page.rect.width, page.rect.height)
                    if extent <= 0:
                        raise LibraryError('First page unavailable; use the file-type icon.', 409)
                    scale = min(1.0, 240 / extent)
                    raw = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes('png')
            except (RuntimeError, ValueError) as error:
                raise LibraryError('PDF preview unavailable; use the file-type icon.', 409) from error
            images[doc['sha256']] = raw
            while len(images) > 64:
                images.popitem(last=False)
        images.move_to_end(doc['sha256'])
    return send_file(BytesIO(raw), mimetype='image/png')


def register_native_library(app):
    app.extensions['native_library_csrf']=token_urlsafe(32)
    app.extensions['native_library_thumbnails']={'images':OrderedDict(), 'lock':Lock()}
    app.register_blueprint(files)


@files.get('/library/files/folder-choices')
@protect
def folder_choices():
    parent=request.args.get('parent_id') or None
    return jsonify(service().children(parent,offset=request.args.get('offset',0)))


@files.post('/library/files/<document_id>/lifecycle')
@protect
def lifecycle(document_id):
    data=payload({'action','enabled'})
    action=data.get('action');lib=service()
    if action=='trash': lib.trash(document_id)
    elif action=='restore': lib.restore(document_id)
    elif action=='favorite': lib.favorite(document_id,data.get('enabled'))
    else: raise LibraryError('Choose a valid file action.')
    return jsonify(document=view_document(lib.get(document_id)))


@files.post('/library/files/bulk')
@protect
def bulk():
    data=payload({'ids','action','folder_id','confirm_scope'})
    ids=data.get('ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=100 or len(set(ids))!=len(ids):
        raise LibraryError('Select between 1 and 100 distinct files.')
    results=[];lib=service()
    for identity in ids:
        try:
            if data['action']=='trash':lib.trash(identity)
            elif data['action']=='restore':lib.restore(identity)
            elif data['action'] in ('move','copy'):
                doc=lib.get(identity)
                with lib.connection() as con: binding=lib._binding(con,data.get('folder_id'))
                destination=binding['course_id'] if binding else None
                if destination!=doc['subject_id'] and data.get('confirm_scope') is not True:
                    raise LibraryError('Confirm changing the subject scope for these files.',409)
                if data['action']=='copy':lib.copy(identity,folder_id=data.get('folder_id'))
                else:lib.update(identity,folder_id=data.get('folder_id'))
            else:raise LibraryError('Choose a valid bulk action.')
            results.append({'id':identity,'ok':True})
        except LibraryError as error:results.append({'id':identity,'ok':False,'error':str(error)})
    return jsonify(results=results)


@files.route('/library/files/templates/<folder_id>',methods=['GET','POST'])
@protect
def template(folder_id):
    data=payload({'key','confirm'}) if request.method=='POST' else {'key':request.args.get('key')}
    return jsonify(service().apply_template(folder_id,data.get('key'),confirm=data.get('confirm') is True))


@files.post('/library/files/<document_id>/repair')
@protect
def repair(document_id):
    chosen=request.files.get('file')
    if chosen is None or len(request.files.getlist('file'))!=1:raise LibraryError('Choose one original to repair.')
    return jsonify(document=view_document(service().repair_original(document_id,chosen.stream)))


def synchronize_academic_folders(lib, courses):
    terms={}
    for course in courses:
        value=str(course.get('semester','')).strip().casefold()
        match=re.match(r'(?:semester\s*|sem\s*)?([1-8])(?:\s|$)',value)
        number=int(match[1]) if match else 1 if value=='first semester' else None
        year=str(course.get('academic_year','')).strip()
        if year.casefold() in ('academic year unspecified','unspecified'):year=''
        if number is not None: terms.setdefault((number,year),[]).append(course)
    for (number,year),configured in sorted(terms.items()): lib.bootstrap_academics(configured,number=number,year=year or None)


def initialize_library(app):
    """Explicit startup owner: migration and folder projection never run on GET."""
    import config
    supplied=app.config.get('NATIVE_LIBRARY_SERVICE')
    if supplied is not None: return supplied
    database=Path(app.config.get('ACADEMIC_DATABASE_PATH') or config.DATABASE_PATH)
    # Do not initialize/migrate beside an absent or foreign academic owner.
    # The normal launcher explicitly activates its canonical schema first.
    if not database.is_file(): return None
    from contextlib import closing
    with closing(sqlite3.connect(database.absolute().as_uri()+'?mode=ro',uri=True)) as academic:
        if not academic.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_documents'").fetchone(): return None
    root=Path(app.config.get('NATIVE_LIBRARY_ROOT') or Path(config.DATA_PATH)/'native_library')
    lib=NativeDocumentLibrary(root,autostart=False)
    try:
        if database.is_file():
            lib.migrate_legacy_sources(database)
            publisher=app.extensions.get('academic_wal_publisher')
            lib.configure_tutor(database,app.config.get('TUTOR_INDEX_ROOT',root.parent/'tutor_retrieval'),refresh=publisher.request_refresh if publisher else None)
        with app.app_context():
            courses=catalogue().get('courses',[])
            synchronize_academic_folders(lib,courses)
            lib.synchronize_course_scopes(database,courses)
        app.extensions['native_document_library']=lib
        lib.start_worker()
        return lib
    except BaseException:
        lib.close()
        raise


@files.get('/library/registered/<source_id>/original')
@protect
def registered_original(source_id):
    """Read-only compatibility resolver for explicitly configured legacy roots."""
    from io import BytesIO
    from personal_learning_assistant.learning_studio.sources import RegisteredSources
    from personal_learning_assistant.learning_studio.validation import PackageError
    import config
    loader=RegisteredSources(current_app.config.get('LEARNING_STUDIO_SOURCE_DATABASE',config.DATABASE_PATH),
                             current_app.config.get('LEARNING_STUDIO_SOURCE_ROOTS',{}))
    try:raw=loader(source_id)
    except (PackageError,ValueError,OSError,sqlite3.Error):
        raise LibraryError('Registered original is unavailable or its hash changed. Configure its existing source root or repair the exact original; study history is preserved.',409)
    response=send_file(BytesIO(raw),mimetype='application/pdf',as_attachment=request.args.get('download')=='1',download_name='registered-original.pdf')
    response.headers['Content-Security-Policy']='sandbox'
    return response
