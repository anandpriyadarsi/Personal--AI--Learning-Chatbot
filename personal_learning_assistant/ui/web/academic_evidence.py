"""Local-owner evidence UI. GETs read RAM; only a signed explicit intent writes."""
from datetime import datetime, timezone
from io import BytesIO
from secrets import token_bytes
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfoNotFoundError
from flask import Blueprint, current_app, jsonify, redirect, render_template, request, send_file
from itsdangerous import BadSignature, URLSafeTimedSerializer
from personal_learning_assistant.learning_studio.validation import PackageError, require, integer
from personal_learning_assistant.learning_studio.educational_projection import build_preview, tutor_handoff

def register_academic_evidence(app):
    bp=Blueprint('academic_evidence',__name__)
    signer=URLSafeTimedSerializer(token_bytes(32),salt='academic-evidence-v23')

    def service():
        factory=current_app.config.get('ACADEMIC_EVIDENCE_SERVICE_FACTORY')
        if factory:return factory()
        from personal_learning_assistant.services.academic_evidence_service import AcademicEvidenceService
        from .learning_studio import service as learning_owner
        import config as installed
        try:
            return AcademicEvidenceService(current_app.config.get('ACADEMIC_DATABASE_PATH',installed.DATABASE_PATH),
                studio=learning_owner(),wal_snapshot_provider=current_app.config.get('ACADEMIC_WAL_SNAPSHOT_PROVIDER'),
                local_timezone=current_app.config.get('ACADEMIC_TIMEZONE','Asia/Kolkata'))
        except (ValueError,ZoneInfoNotFoundError) as error:
            raise PackageError('Choose a valid academic timezone.',400) from error

    @bp.before_request
    def boundary():
        if current_app.config.get('ACADEMIC_EVIDENCE_ENABLED',True) is not True:
            return 'Academic evidence is disabled.',404
        if request.method=='POST':
            request.max_content_length=20000
            origin=request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site')=='cross-site' or (
                    origin and (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.scheme,request.host)):
                return 'Cross-site academic actions are not allowed.',403

    @bp.after_request
    def no_store(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @bp.errorhandler(PackageError)
    def invalid(error):
        if request.args.get('format')=='json' or request.path.endswith('/tutor-handoff'):
            return jsonify(error=str(error)),error.status
        return render_template('academic_evidence.html',active_page='evidence',stage='error',
            error_message=str(error)),error.status

    def query(allowed):
        require(set(request.args)<=set(allowed) and all(len(request.args.getlist(k))==1 for k in request.args),
            'Unsupported or repeated evidence query.')

    def context(module_id,revision):
        s=service()
        frozen,cat=s.frozen_learning(module_id,revision)
        # Bind the Learning side to one captured owner image for this response.
        from copy import copy
        bound=copy(s);bound.studio=frozen
        view=bound.learning(module_id,revision)
        preview=build_preview(frozen,module_id,revision,catalogue=cat,as_of=s.now())
        require(preview['source']['sha256']==view.source_sha256,'Learning source changed; reload.',409)
        return s,view,preview,frozen,cat

    def signed(view,kind,**extra):
        return signer.dumps({'kind':kind,'module_id':view.module_id,'revision':view.module_revision,
            'fingerprint':view.fingerprint,**extra})

    def verified(token,module_id,revision,kind):
        try:
            value=signer.loads(token,max_age=900)
            if (not isinstance(value,dict) or value.get('kind')!=kind or
                    value.get('module_id')!=module_id or value.get('revision')!=revision):
                raise ValueError()
            return value
        except (BadSignature,ValueError,TypeError) as error:
            raise PackageError('Invalid or expired context. Open a fresh preview.',400) from error

    @bp.get('/academic-evidence')
    def index():
        query(set())
        s=service();cat=s.catalogue();lessons=[];message=''
        try:
            from personal_learning_assistant.learning_studio.read_snapshot import frozen_studio
            frozen=frozen_studio(s.studio,catalogue=cat)
            with frozen.store.connection() as con:
                lessons=[dict(r) for r in con.execute('SELECT m.module_id,m.revision,m.title,m.course_id FROM modules m JOIN active_modules a USING(module_id,revision) ORDER BY m.module_id LIMIT 101')]
            require(len(lessons)<=100,'Lesson list exceeds its bounded inventory.',503)
        except PackageError:
            message='Registered learning material is unavailable. Existing records were not changed.'
        return render_template('academic_evidence.html',active_page='evidence',stage='index',
            catalogue=cat,lessons=lessons,error_message=message)

    @bp.get('/academic-evidence/learning/<module_id>/<int:revision>')
    def learning(module_id,revision):
        query({'format'})
        require(request.args.get('format','html') in {'html','json'},'Unsupported evidence format.')
        s,view,preview,_,_=context(module_id,revision)
        if request.args.get('format')=='json':return jsonify(view.to_dict())
        from personal_learning_assistant.learning_studio.rendering import markdown, trusted_graph, trusted_activity
        def extension(block,widget_id):
            original={'kind':block['kind'],'pages':block['pages'],**block['content']}
            return trusted_graph(original) if block['kind']=='graph' else trusted_activity(original,widget_id)
        from personal_learning_assistant.services.learning_tutor_session_v24 import project_session_metadata_snapshot
        return render_template('academic_evidence.html',active_page='evidence',stage='lesson',
            view=view,preview=preview,markdown=markdown,extension=extension,error_message='',
            review_token=signed(view,'review'),history=project_session_metadata_snapshot(s,view))

    @bp.get('/academic-evidence/learning/<module_id>/<int:revision>/source.pdf')
    def source(module_id,revision):
        query(set())
        s=service();frozen,cat=s.frozen_learning(module_id,revision)
        preview=build_preview(frozen,module_id,revision,catalogue=cat,as_of=s.now())
        response=send_file(BytesIO(frozen.source(module_id,revision)),mimetype='application/pdf',
            download_name=preview['source']['filename'],as_attachment=False)
        response.headers['Content-Security-Policy']='sandbox'
        return response

    @bp.get('/academic-evidence/learning/<module_id>/<int:revision>/assets/<name>')
    def asset(module_id,revision,name):
        query(set())
        import re
        require(re.fullmatch(r'[A-Za-z0-9_.-]+\.(png|jpg|jpeg|webp)',name) is not None,'Unsupported owned image.',404)
        s=service();frozen,cat=s.frozen_learning(module_id,revision)
        build_preview(frozen,module_id,revision,catalogue=cat,as_of=s.now())
        raw=frozen.asset(module_id,revision,'assets/'+name)
        mime='image/jpeg' if name.endswith(('.jpg','.jpeg')) else 'image/'+name.rsplit('.',1)[1]
        return send_file(BytesIO(raw),mimetype=mime)

    @bp.get('/academic-evidence/learning/<module_id>/<int:revision>/study-preview')
    def study_preview(module_id,revision):
        query({'minutes'})
        try:minutes=int(request.args.get('minutes','30'))
        except (ValueError,TypeError) as error:raise PackageError('Choose 1–180 practice minutes.') from error
        integer(minutes,1,180)
        _,view,preview,_,_=context(module_id,revision)
        require(view.manual_task_allowed,'Current source and mapping are required for a linked manual study task.',409)
        token=signed(view,'study',minutes=minutes,intent_id=str(uuid4()))
        return render_template('academic_evidence.html',active_page='evidence',stage='preview',
            view=view,preview=preview,minutes=minutes,intent_token=token,error_message='')

    @bp.post('/academic-evidence/learning/<module_id>/<int:revision>/study-intent')
    def study_intent(module_id,revision):
        require(set(request.form)=={'intent_token'} and len(request.form.getlist('intent_token'))==1,'Unsupported study intent.')
        payload=verified(request.form['intent_token'],module_id,revision,'study')
        _,view,preview,_,_=context(module_id,revision)
        require(view.manual_task_allowed and payload.get('fingerprint')==view.fingerprint,
            'Academic context changed. Preview the study choice again.',409)
        from personal_learning_assistant.services.operational_task_service import OperationalTaskConflictError, OperationalTaskValidationError, OperationalTaskUnavailableError
        from .routes import _operational_planner_service
        try:
            owner=_operational_planner_service().tasks
            mapping=preview['mapping']
            owner.create_manual_study_task(intent_id=payload['intent_id'],
                title=('Manual practice: '+view.module_title)[:300],
                description='Student-selected low-stakes practice. Module '+module_id+' revision '+str(revision)+
                    '; source SHA256 '+view.source_sha256+'. Independence and mastery remain unknown.',
                course_id=view.course_id,topic_id=view.topic_id,topic_name=mapping['topic_name'],
                estimated_minutes=payload['minutes'])
        except OperationalTaskConflictError as error:raise PackageError(str(error),409) from error
        except OperationalTaskValidationError as error:raise PackageError(str(error),400) from error
        except (OperationalTaskUnavailableError,ZoneInfoNotFoundError) as error:
            raise PackageError('The Planner owner is unavailable; no study approval is claimed.',503) from error
        return redirect('/planning/tasks?created=1&course_id='+view.course_id,code=303)

    @bp.post('/academic-evidence/learning/<module_id>/<int:revision>/note-draft')
    def note_draft(module_id,revision):
        require(not current_app.config.get('ANDROID_LOCAL_RUNTIME'),
            'PDF draft conversion is unavailable in this Android build. Read the locally extracted Library text or import an authored Learning package.',422)
        query(set())
        require(set(request.form)=={'review_token'} and len(request.form.getlist('review_token'))==1,
            'Unsupported draft review request.')
        payload=verified(request.form['review_token'],module_id,revision,'review')
        _,view,_,frozen,_=context(module_id,revision)
        require(payload.get('fingerprint')==view.fingerprint,'Academic context changed. Reload before conversion.',409)
        from personal_learning_assistant.learning_studio.note_draft import convert
        draft=convert(frozen.source(module_id,revision),media_type='application/pdf')
        return render_template('note_draft.html',active_page='evidence',view=view,draft=draft)

    @bp.post('/academic-evidence/learning/<module_id>/<int:revision>/tutor-help')
    def tutor_help(module_id,revision):
        query(set())
        fields={'review_token','event_id','question_id','level'}
        require(set(request.form)==fields and all(len(request.form.getlist(k))==1 for k in fields),
            'Unsupported offline help request.')
        payload=verified(request.form['review_token'],module_id,revision,'review')
        _,view,preview,_,_=context(module_id,revision)
        require(payload.get('fingerprint')==view.fingerprint,'Academic context changed. Reload before help.',409)
        from personal_learning_assistant.learning_studio.grounded_help import consume, LEVELS
        from personal_learning_assistant.learning_studio.rendering import markdown
        help_view=consume(preview,view,event_id=request.form['event_id'],question_id=request.form['question_id'],
            level=request.form['level'],explicit_action=True)
        from .learning_tutor_v24 import learning_tutor_v24_url
        return render_template('grounded_help.html',active_page='evidence',view=view,help=help_view,
            levels=LEVELS,review_token=signed(view,'review'),markdown=markdown,
            save_help_url=learning_tutor_v24_url(module_id,revision,help_view['event_id'],help_view['question']['id'],help_view['assistance_level']))

    @bp.post('/academic-evidence/learning/<module_id>/<int:revision>/tutor-handoff')
    def tutor_context(module_id,revision):
        require(set(request.form)=={'review_token','student_question','page'} and
            all(len(request.form.getlist(k))==1 for k in request.form),'Unsupported Tutor handoff.')
        payload=verified(request.form['review_token'],module_id,revision,'review')
        s,view,_,frozen,cat=context(module_id,revision)
        require(payload.get('fingerprint')==view.fingerprint,'Academic context changed. Reload before Tutor handoff.',409)
        try:page=int(request.form['page'])
        except ValueError as error:raise PackageError('Choose an exact source page.') from error
        result=tutor_handoff(frozen,{'module_id':module_id,'module_revision':revision,
            'source_sha256':view.source_sha256,'pages':[page],'student_question':request.form['student_question']},
            catalogue=cat,as_of=s.now())
        return jsonify(result)

    app.register_blueprint(bp)
