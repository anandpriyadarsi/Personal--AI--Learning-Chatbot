"""Explicit source-grounded study choices; external content remains read-only."""
from uuid import uuid4
from flask import Blueprint,current_app,request,render_template,redirect,url_for
from itsdangerous import BadSignature
from personal_learning_assistant.services.operational_task_service import OperationalTaskConflictError,OperationalTaskValidationError,OperationalTaskError
from personal_learning_assistant.services.obsidian_workspace_service import ObsidianWorkspaceError


def register_pao_sources(app):
    bp=Blueprint('pao_sources',__name__)

    def owners():
        from .routes import _operational_planner_service,_obsidian_workspace_service
        return _operational_planner_service().tasks,_obsidian_workspace_service()

    @bp.route('/planning/source/obsidian/preview')
    def preview():
        if not current_app.config.get('PAO_V3_ENABLED'):
            return 'Activate PAO to create a source-linked study task.',409
        try:
            tasks,workspace=owners()
            note=workspace.validate_note_version(request.args.get('path',''))
            if not note.get('source_item_id') or note.get('identity_conflict'):
                return 'Refresh the source manifest and resolve duplicate IDs before planning study.',409
            payload={'purpose':'obsidian-study','intent_id':str(uuid4()),'source_id':note['source_item_id'],
                'connection_id':note['connection_id'],'path':note['relative_path'],'sha256':note['source_hash']}
            token=current_app.extensions['pao_command_signer'].dumps(payload)
            return render_template('pao_source_preview.html',active_page='planning',note=note,
                intent_token=token,catalogue=tasks.repository.capture_catalogue())
        except ObsidianWorkspaceError:
            return 'This source is changed or unavailable. Refresh its manifest before planning study.',409
        except OperationalTaskError:
            return 'Planner storage is unavailable.',503

    @bp.post('/planning/source/obsidian/accept')
    def accept():
        if not current_app.config.get('PAO_V3_ENABLED'):
            return 'Activate PAO before planning study.',409
        try:
            payload=current_app.extensions['pao_command_signer'].loads(request.form.get('intent_token',''),max_age=900)
            if payload.get('purpose') != 'obsidian-study':
                raise ValueError()
            tasks,workspace=owners()
            note=workspace.validate_note_version(payload['path'],payload['sha256'])
            if (note.get('identity_conflict') or note['source_item_id']!=payload['source_id']
                    or note['connection_id']!=payload['connection_id']):
                return 'The source identity changed. Preview it again.',409
            task=tasks.create_task(title=request.form.get('title',''),
                estimated_minutes=request.form.get('estimated_minutes',''),due_on=request.form.get('due_on'),
                course_id=request.form.get('course_id') or None,topic_id=request.form.get('topic_id') or None,
                description='Explicit study of external Markdown; source '+payload['source_id']+' SHA256 '+payload['sha256']+'. Mapping unreviewed; no assessed outcome.',
                _intent_id=payload['intent_id'],_source_refs=({'owner':'obsidian','kind':'markdown','identifier':payload['source_id'],
                    'revision_key':payload['sha256'],'sha256':payload['sha256'],'mapping_status':'unreviewed'},))
            return redirect(url_for('web.planning_tasks',status='all',_anchor='task-'+task['id']),code=303)
        except (BadSignature,ValueError,KeyError,TypeError):
            return 'Invalid or expired source choice. Preview it again.',400
        except (ObsidianWorkspaceError,OperationalTaskConflictError):
            return 'This source or saved intent changed. Preview it again.',409
        except OperationalTaskValidationError as error:
            return str(error),400
        except OperationalTaskError:
            return 'Planner storage is unavailable.',503

    @bp.get('/planning/source/obsidian/<source_id>')
    def open_source(source_id):
        _,workspace=owners()
        config=workspace._load_config()
        manifest=config.get('source_manifest') or {}
        row=next((r for r in manifest.get('items',[]) if r['id']==source_id and r.get('state')!='missing'),None)
        if row is None:
            return 'The linked source is unavailable in this connection. Its historical reference is preserved.',409
        try:
            workspace.validate_note_version(row['relative_path'],request.args.get('sha256',''))
        except ObsidianWorkspaceError:
            return 'The linked source version changed. Review the current source in Obsidian before replanning.',409
        return redirect(url_for('web.obsidian_note',path=row['relative_path']),code=303)

    app.register_blueprint(bp)
