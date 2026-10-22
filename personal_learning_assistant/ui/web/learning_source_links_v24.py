"""Read-only discovery between exact registered PDFs and existing Learning pages."""
from urllib.parse import urlencode
from flask import Blueprint, current_app, jsonify, render_template, request
from personal_learning_assistant.learning_studio.validation import PackageError, require
from personal_learning_assistant.services.learning_source_links_v24 import LearningSourceLinksV24, source_identity


def _enabled():
    return all(current_app.config.get(key,True) is True for key in
        ('ACADEMIC_EVIDENCE_ENABLED','LEARNING_LIBRARY_ENABLED','LEARNING_SOURCE_LINKS_V24_ENABLED'))


def source_links_target(document_id, content_hash):
    """Only build an exact-identity discovery URL; no source lookup or file access."""
    if not _enabled():return None
    try:source_identity(document_id,content_hash)
    except PackageError:return None
    return '/learning/source-links?'+urlencode({'document_id':document_id,'content_hash':content_hash})


def _service():
    factory=current_app.config.get('LEARNING_SOURCE_LINKS_V24_SERVICE_FACTORY')
    if factory is not None:return factory()
    from .routes import _learning_library_service, _knowledge_reader_service
    from .learning_studio import service as learning_owner
    from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
    import config as installed
    studio=learning_owner()
    evidence_factory=current_app.config.get('ACADEMIC_EVIDENCE_SERVICE_FACTORY')
    evidence=(evidence_factory() if evidence_factory is not None else AcademicEvidenceService(
        current_app.config.get('ACADEMIC_DATABASE_PATH',installed.DATABASE_PATH),
        studio=studio,wal_snapshot_provider=current_app.config.get('ACADEMIC_WAL_SNAPSHOT_PROVIDER'),
        local_timezone=current_app.config.get('ACADEMIC_TIMEZONE','Asia/Kolkata')))
    return LearningSourceLinksV24(evidence,
        library_database_path=_learning_library_service().repository.database_path,
        knowledge_database_path=_knowledge_reader_service().database_path,
        learning_database_path=studio.store.path)


def register_learning_source_links_v24(app):
    bp=Blueprint('learning_source_links_v24',__name__)

    @bp.before_request
    def boundary():
        if not _enabled():return 'Learning source links are disabled.',404

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @bp.errorhandler(PackageError)
    def invalid(error):
        if request.args.get('format')=='json':return jsonify(error=str(error)),error.status
        return render_template('learning_source_links_v24.html',active_page='library',
            view=None,error_message=str(error)),error.status

    @bp.get('/learning/source-links')
    def index():
        allowed={'document_id','content_hash','format','offset','limit'}
        require(set(request.args)<=allowed and all(len(request.args.getlist(k))==1 for k in request.args),
            'Unsupported or repeated source links query.')
        require(request.args.get('format','html') in {'html','json'},'Unsupported source links format.')
        document_id=request.args.get('document_id');content_hash=request.args.get('content_hash')
        source_identity(document_id,content_hash)
        try:offset=int(request.args.get('offset','0'));limit=int(request.args.get('limit','10'))
        except (ValueError,TypeError) as error:raise PackageError('Invalid source links pagination.') from error
        view=_service().project(document_id,content_hash,offset=offset,limit=limit)
        if request.args.get('format')=='json':return jsonify(view)
        base=source_links_target(document_id,content_hash)
        previous=(base+'&'+urlencode({'offset':max(0,offset-limit),'limit':limit})) if offset else None
        following=(base+'&'+urlencode({'offset':offset+limit,'limit':limit})) if view['has_more'] else None
        return render_template('learning_source_links_v24.html',active_page='library',
            view=view,error_message='',previous_url=previous,next_url=following)

    app.register_blueprint(bp)
