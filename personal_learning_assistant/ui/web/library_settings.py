"""Local web backup, staged restore and explicit catalogue refresh."""
from pathlib import Path
import sqlite3
from flask import Blueprint,current_app,render_template,request,jsonify,send_file,redirect
from .native_library import protect,service,synchronize_academic_folders,catalogue
settings=Blueprint('library_settings',__name__)


def root():
    import config
    return Path(current_app.config.get('LOCAL_DATA_ROOT',config.BASE_PATH))


@settings.get('/library/upload')
def legacy_upload():
    return redirect('/library/files',code=302)


@settings.get('/library/settings')
def home():
    return render_template('library_settings.html',active_page='library',
        csrf_token=current_app.extensions['native_library_csrf'],message='',usage=service().storage_usage())


@settings.get('/library/backup/export')
def export():
    from personal_learning_assistant.android_backup import export_backup_file
    try:path=export_backup_file(root())
    except (ValueError,OSError,sqlite3.Error):
        return 'Backup could not be verified. Existing data is unchanged. Check free space and retry.',409
    response=send_file(path,mimetype='application/zip',as_attachment=True,download_name='ANVAYA-private-backup.zip')
    response.call_on_close(lambda:path.unlink(missing_ok=True))
    response.headers['Cache-Control']='no-store'
    return response


def csrf():
    import hmac
    token=request.form.get('csrf_token','')
    origin=request.headers.get('Origin')
    return (hmac.compare_digest(token,current_app.extensions['native_library_csrf']) and
            (not origin or origin.rstrip('/')==request.host_url.rstrip('/')) and
            request.headers.get('Sec-Fetch-Site')!='cross-site')


@settings.post('/library/backup/restore')
def restore():
    from personal_learning_assistant.android_backup import stage_restore,MAX_BYTES
    if not csrf():return 'Reload Library settings and retry.',403
    request.max_content_length=MAX_BYTES+1024*1024
    upload=request.files.get('backup')
    if upload is None:return 'Choose a complete ANVAYA backup.',400
    try:stage_restore(root(),upload.stream)
    except (ValueError,OSError,sqlite3.Error):return 'Backup rejected. Existing data was kept.',400
    return render_template('library_settings.html',active_page='library',
        csrf_token=current_app.extensions['native_library_csrf'],usage=service().storage_usage(),
        message='Backup verified and staged. Save or pause work, stop this web server with Ctrl+C, then run python phase7_web.py again. The previous data directory is retained for recovery.')


@settings.post('/library/settings/refresh-courses')
def refresh_courses():
    if not csrf():return 'Reload Library settings and retry.',403
    courses=catalogue().get('courses',[])
    lib=service();synchronize_academic_folders(lib,courses)
    if getattr(lib,'_tutor_database',None):lib.synchronize_course_scopes(lib._tutor_database,courses)
    return redirect('/library/files',code=303)


def register_library_settings(app):app.register_blueprint(settings)
