"""Synthetic UC100N journey in real Chromium; no provider network or invented marks."""
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
from threading import Thread
import pytest
from werkzeug.serving import make_server
from .test_multilecture_web import source_pdf,reviewed
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Enable real Chromium with ANVAYA_BROWSER_TESTS=1')


def setup_journey(tmp_path):
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.services.assessment_package_service import AssessmentPackageService
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationService
    from personal_learning_assistant.services.assessment_intelligence_service import AssessmentIntelligenceService
    from personal_learning_assistant.services.academic_agent_web_service import AcademicAgentWebService
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    from tests.test_assessment_studio_phase_b import _package
    database=tmp_path/'data/learning_assistant.db';database.parent.mkdir()
    apply_migrations(database)
    now='2026-11-04T10:00:00Z'
    with sqlite3.connect(database) as con:
        con.execute("INSERT INTO courses(id,code,name,status,description,created_at,updated_at) VALUES('c0','UC100N','Data Science and Artificial Intelligence','active','Synthetic demo',?,?)",(now,now))
        con.execute("INSERT INTO topics(id,course_id,name,normalized_name,position,status,created_at,updated_at) VALUES('t0','c0','Centering','centering',1,'not_started',?,?)",(now,now))
    cat={'available':True,'courses':[{'id':'c0','code':'UC100N','name':'Data Science and Artificial Intelligence','academic_year':'2026–27','semester':'Semester 1','topics':[{'id':'t0','name':'Centering'}]}]}
    lib=NativeDocumentLibrary(database.parent/'native_library',autostart=False)
    subject=lib.bootstrap_academics(cat['courses'])['subjects'][0]
    folder=lib.create_folder("Professor's Lectures",subject['folder_id'])
    index=tmp_path/'retrieval';lib.configure_tutor(database,index);lib.start_worker()
    studio=LearningStudioService(database.parent/'learning_studio.sqlite3',source_loader=lambda _:None,catalogue_loader=lambda:cat)
    pack=_package(package_id='uc100n.synthetic.centering');pack['assessment'].update(course={'code':'UC100N','name':'Data Science and Artificial Intelligence'},title='Centering formal quiz',total_marks=1)
    q=copy.deepcopy(pack['questions'][0]);q.update(text='When the batch mean is 1, what is the centered value of 3?',marks=1,negative_marks=0,
        options=[{'id':'A','text':'0'},{'id':'B','text':'2'}],solution='Subtract the mean: 3 - 1 = 2.')
    q['academic_map'].update(topic='Centering',chapter='Data preprocessing',subtopic='Mean centering',concepts=['centering'])
    pack['questions']=[q]
    packages=AssessmentPackageService(database)
    batch=packages.stage_upload('quiz.json',json.dumps(pack).encode());approved=packages.approve(batch['id'])
    aid=approved
    runner=AssessmentRunnerService(database);evaluation=AssessmentEvaluationService(database);reports=AssessmentIntelligenceService(database)
    class Provider:
        configured=True
        def complete(self,request):
            return TutorProviderResponse('The synthetic batch mean is 1; subtracting it centers an observation. [S1]','synthetic-only','fixture')
    tutor=AcademicAgentWebService(database_path=database,index_root=index,course_catalogue_loader=lambda:cat,provider_factory=Provider)
    app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:cat,
        'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio,'ASSESSMENT_PACKAGE_SERVICE_FACTORY':lambda:packages,
        'ASSESSMENT_RUNNER_SERVICE_FACTORY':lambda:runner,'ASSESSMENT_EVALUATION_SERVICE_FACTORY':lambda:evaluation,
        'ASSESSMENT_INTELLIGENCE_SERVICE_FACTORY':lambda:reports,'ACADEMIC_AGENT_WEB_SERVICE_FACTORY':lambda:tutor})
    return app,lib,studio,folder,aid,tutor,runner,evaluation


@pytest.mark.parametrize('width,zoom',[(390,1),(768,1),(1366,1),(768,2)])
def test_originals_tutor_authoring_quickcheck_formal_results_resume(tmp_path,width,zoom):
    from playwright.sync_api import sync_playwright,expect
    from personal_learning_assistant.learning_studio.multilecture_authoring import RUBRIC
    app,lib,studio,folder,aid,tutor,runner,evaluation=setup_journey(tmp_path)
    server=make_server('127.0.0.1',0,app,threaded=True);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':width,'height':900},accept_downloads=True,reduced_motion='reduce')
            page=context.new_page();errors=[];external=[];page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base+'/') else None);page.on('pageerror',lambda error:errors.append(str(error)))
            # Exercise actual doubled rendering in addition to narrow viewports.
            if zoom==2:
                context.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.zoom='2';});")
            page.goto(base+'/library/files?folder_id='+folder['id'])
            page.get_by_label('Add files or folder').click();page.get_by_role('button',name='Import files',exact=True).first.click()
            originals=[source_pdf(f'Lecture {i}: synthetic batch mean is {i}. Center observations by subtracting the batch mean.') for i in range(1,5)]
            page.locator('#import-form input[type=file]').set_input_files([{'name':f'Lecture-{i}.pdf','mimeType':'application/pdf','buffer':raw} for i,raw in enumerate(originals,1)])
            page.locator('#import-form button[type=submit]').click()
            expect(page.locator('#import-results')).to_contain_text('Lecture-4.pdf · Saved')
            page.get_by_role('button',name='Done · Show saved files').click()
            expect(page.locator('.file-row')).to_have_count(4)
            expect(page.locator('[data-status]').first).to_have_text('Ready for Tutor',timeout=30000)
            docs=sorted(lib.list_documents(folder_id=folder['id'])['items'],key=lambda d:d['original_name'])
            page.locator('.file-main a').filter(has_text='Lecture-1.pdf').click()
            expect(page.locator('#pdf-page')).to_be_visible()
            assert page.request.get(base+f'/library/files/{docs[0]["id"]}/original').body()==originals[0]
            # Actual retrieval generation and grounded Tutor session; provider is synthetic.
            sid=tutor.create_session(course_id='c0',source_policy='source_only',title='Centering evidence')
            page.goto(base+'/agent/sessions/'+sid);page.locator('#agent-question').fill('What is the synthetic batch mean in Lecture 1?')
            page.get_by_role('button',name='Ask tutor',exact=True).click()
            expect(page.locator('.tutor-transcript')).to_contain_text('synthetic batch mean',timeout=20000)
            assert tutor.session_view(sid)['turns'][-1]['evidence']
            page.goto(base+'/learning/author');page.locator('input[name=title]').fill('Mean centering across four lectures')
            page.locator('select[name=course_id]').select_option('c0');page.locator('select[name=topic_id]').select_option('t0')
            page.locator('input[name=order]').fill(','.join(d['id'] for d in docs))
            page.get_by_role('button',name='Prepare local source draft').click();page.wait_for_url('**/learning/author/*')
            token=page.url.rsplit('/',1)[1];p=reviewed(studio,token)
            page.get_by_text('Advanced package editor',exact=True).click()
            page.locator('input[name=advanced_json]').check();page.locator('#author-package').fill(json.dumps(p))
            for item in RUBRIC:page.locator(f'input[name=review][value={item}]').check()
            page.get_by_role('button',name='Validate and stage preview').click();page.wait_for_url('**/learning/staged/**')
            page.get_by_role('button',name='Publish',exact=False).click();page.wait_for_url('**/learning/modules/**')
            module=p['module_id'];url=base+f'/learning/modules/{module}/1'
            page.goto(url+'?view=learn&section=lesson-1')
            assert 'correct_index' not in page.content()
            form=page.locator('.ls-inline-question');form.locator('input[type=radio]').first.check();form.locator('button[type=submit]').click()
            expect(form.locator('.ls-feedback')).to_contain_text('Correct',timeout=10000)
            page.get_by_role('button',name='Mark completed and continue',exact=True).click();page.wait_for_url(lambda value:'section=lesson-2' in value,wait_until='domcontentloaded')
            context.close();context=browser.new_context(viewport={'width':width,'height':900})
            if zoom==2:context.add_init_script("document.addEventListener('DOMContentLoaded',()=>{document.documentElement.style.zoom='2';});")
            page=context.new_page()
            page.goto(base+'/learning');expect(page.get_by_role('link',name='Resume: Lecture-2.pdf')).to_be_visible()
            # A real canonical Assessment submission and evaluation, not an imported mark.
            page.goto(base+'/assessments/tests/'+aid);page.locator('input[name=confirmed]').check();page.get_by_role('button',name='Start CBT Test').click()
            page.wait_for_url('**/assessments/sessions/**');assessment_sid=page.url.split('/sessions/')[1].split('/')[0]
            page.locator('input[name=option_ids][value=A]').check();page.get_by_role('button',name='Save & Next',exact=True).click()
            page.on('dialog',lambda dialog:dialog.accept());page.get_by_role('button',name='Submit Test',exact=True).click()
            page.wait_for_url('**/summary');page.get_by_role('button',name='Evaluate / Open Results').click();page.wait_for_url('**/evaluation*')
            assert evaluation.results(assessment_sid)['confirmed_score_milli']==0
            page.goto(url+'?view=learn&section=lesson-2');page.locator('.ls-assessment-feedback summary').click();page.get_by_role('button',name='Show read-only assessment feedback').click()
            page.locator('.ls-assessment-feedback summary').click();expect(page.locator('.ls-assessment-feedback')).to_contain_text('Needs revision')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            output=os.environ.get('ANVAYA_WEB_ARTIFACTS')
            if output:
                Path(output).mkdir(parents=True,exist_ok=True);page.screenshot(path=str(Path(output)/f'journey-{width}-scale-{zoom}.png'),full_page=True)
            assert not errors
            assert not external
            browser.close()
    finally:server.shutdown();thread.join(5);server.server_close();lib.close()
