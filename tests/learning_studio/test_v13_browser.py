"""High-fidelity synthetic journeys, shipped to both CI platforms."""
import copy
import io
import os
import threading
import pytest
from werkzeug.serving import make_server
from .test_browser import browser, no_overflow, screenshot
from .helpers import package, catalogue
from .test_v12_contracts import graph, activity
from personal_learning_assistant.learning_studio.demo import synthetic_pdf
from personal_learning_assistant.learning_studio.coverage import build_coverage
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit browser gate flag required.')

@pytest.fixture
def quality_live(tmp_path):
    from PIL import Image
    raw=synthetic_pdf(20);p=package(raw);p['schema']='anvaya.learning-module.v2';p['source']['page_count']=20
    p['title']='Twenty synthetic lessons for source-grounded reader and exam revision validation'
    image=io.BytesIO();Image.new('RGB',(600,800),'#ecf0f2').save(image,format='PNG')
    assets={f'assets/page-{i}.png':image.getvalue() for i in range(1,21)}
    p['pages']=[{'page':i,'status':'needs_review','text':f'Synthetic source page {i}. Demonstration only. No academic evidence.','review_flags':['Instructor intent and external authenticity are not certified.'],'preview':f'assets/page-{i}.png'} for i in range(1,21)]
    p['sections']=[]
    for i in range(1,21):
        p['sections'].append({'id':f'lesson-{i:02}','title':f'Lesson {i}: preserve the synthetic comparison','pages':[i],'blocks':[
            {'kind':'source','text':p['pages'][i-1]['text'],'pages':[i]},
            {'kind':'teaching','text':f'## Core concept {i}\nKeep the synthetic cases distinct.\n\n### Common trap {i}\nA rereading record is not graded correctness.','pages':[i]},
            {'kind':'objectives','text':'Explain the source-linked distinction without copying.','pages':[i]}]})
    for i in (7,13):
        g=graph();g['pages']=[i];g['nodes'][0]['label']='Long synthetic node label preserving explicit source distinctions and keeping several qualifiers rather than silently dropping information from the representation.'
        a=activity();a['pages']=[i];p['sections'][i-1]['blocks'] += [g,a]
    p['sections'][12]['blocks'].append({'kind':'table','headers':['Synthetic heading preserving all table members '*4,'Comparison'],'rows':[['Very long synthetic table cell '*20,'Contrasting case']],'pages':[13]})
    p['questions']=[dict(copy.deepcopy(p['questions'][0]),id=f'q{i:02}',prompt=f'Synthetic question {i}: which option follows the given source?',pages=[(i-1)%20+1]) for i in range(1,32)]
    p['revision']=[{'kind':'teaching','pages':list(range(1,21)),'text':'# Exam notes\n\n'+'\n\n'.join(f'## Concept {i}\nAll original synthetic list members {i}:\n- Case A\n- Case B\n\n### Trap {i}\nPreserve uncertainty.' for i in range(1,21))}]
    p['revision'] += [{'kind':'recall','pages':[i+1],'text':f'Recall synthetic distinction {i+1}','answer':'Keep both cases and their qualifications.'} for i in range(12)]
    report=build_coverage(p,raw,reviewer='Synthetic fixture author',method='Mechanical source locations; not semantic approval')
    report['unresolved']=[{'id':'synthetic-issue','pages':[13],'snippet':'Synthetic comparison','issue':'Meaning remains unverified','next_action':'Inspect original qualifiers before proposing a new revision.'}]
    s=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=catalogue);s.stage(p,assets,report);s.publish('synthetic',1)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s});server=make_server('127.0.0.1',0,app)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    yield f'http://127.0.0.1:{server.server_port}',s,p
    server.shutdown();t.join(10);server.server_close()


def test_exam_notes_have_real_heading_jumps_and_long_graph_labels_fit(browser,quality_live):
    from playwright.sync_api import expect
    url,s,p=quality_live;page=browser.new_page(viewport={'width':390,'height':844});base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=revision');page.emulate_media(media='print');expect(page.locator('.ls-block-recall details p').first).to_be_visible();page.emulate_media(media='screen')
    outline=page.locator('#ls-revision-outline');expect(outline).to_be_visible();outline.locator('summary').click()
    link=outline.get_by_role('link',name='Concept 20',exact=True);link.click();expect(page.locator(link.get_attribute('href'))).to_be_visible()
    page.goto(base+'?view=learn&section=lesson-13')
    assert page.locator('.ls-relationship-graph svg g').evaluate_all('(nodes)=>nodes.every(g=>{const r=g.querySelector("rect").getBBox(),t=g.querySelector("text").getBBox();return t.y>=r.y&&t.y+t.height<=r.y+r.height})')
    no_overflow(page);page.close()


@pytest.mark.parametrize('width',[360,390,768,1024,1366,1536,1920])
def test_contextual_sidebar_exact_source_mistake_recheck_and_exam_modes(browser,quality_live,width):
    from playwright.sync_api import expect
    url,s,p=quality_live;page=browser.new_page(viewport={'width':width,'height':900});base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=learn&section=lesson-01');rail=page.locator('.ls-lesson-rail')
    if width<=390:
        concept=page.locator('.ls-block-teaching p').last.bounding_box();assert concept and concept['y']+concept['height']<844
    if width>860:
        expect(rail).to_be_visible();before=page.locator('#ls-reading-column').bounding_box()['width'];page.click('#nav-toggle')
        page.wait_for_function('(w)=>document.querySelector("#ls-reading-column").getBoundingClientRect().width>w+150',arg=before);page.click('#nav-toggle')
    else:
        page.click('#nav-toggle');expect(rail).to_be_visible();page.locator('#ls-close-rail').click();expect(page.locator('#nav-toggle')).to_be_focused()
        page.click('#nav-toggle');page.keyboard.press('Tab');assert page.evaluate('document.querySelector("#app-sidebar").contains(document.activeElement)')
        page.keyboard.press('Escape');expect(page.locator('#nav-toggle')).to_be_focused()
    page.goto(base+'?view=learn&section=lesson-13');expect(page.locator('.ls-lesson > h2')).to_contain_text('Lesson 13')
    page.locator('.ls-teachback-input').fill('Preserve both cases and the qualification.');page.locator('.ls-save-teachback').click();expect(page.locator('.ls-teachback-status')).to_contain_text('Self-report saved');page.reload();expect(page.locator('.ls-teachback-input')).to_have_value('Preserve both cases and the qualification.')
    screenshot(page,f'v13-lesson13-{width}.png');no_overflow(page)
    page.goto(base+'?view=learn&section=lesson-20');expect(page.locator('.ls-lesson > h2')).to_contain_text('Lesson 20')
    page.goto(base+'?view=practice&question=q31');expect(page.locator('.ls-question-state')).to_contain_text('never practised')
    assert 'correct_index' not in page.content() and 'Compare the original source.' not in page.content()
    form=page.locator('.ls-question');form.locator('input[value="0"]').check();form.locator('button[type=submit]').click();expect(page.locator('.ls-feedback')).to_contain_text('Incorrect')
    form.locator('.ls-source-chips a').click();assert 'question=q31' in page.url and 'page=11' in page.url
    page.get_by_role('link',name='12',exact=True).click();assert 'question=q31' in page.url
    expect(page.locator('#ls-reading-status')).to_contain_text('Reading position saved');assert s.reading_state('synthetic',1)['current'].get('question_id')=='q31'
    page.goto(base);page.locator('#ls-resume').click();assert 'question=q31' in page.url and 'page=12' in page.url
    page.locator('#ls-return-question').click();expect(form).to_have_attribute('data-question-id','q31');form.locator('input[value="1"]').check();form.locator('button[type=submit]').click();expect(page.locator('.ls-feedback')).to_contain_text('Correct retry recorded')
    expect(page.locator('.ls-question-state')).to_contain_text('recovered needs recheck');count=s.evidence()['attempts'];page.locator('.ls-deliberate-recheck').click()
    assert form.locator('input:checked').count()==0 and s.evidence()['attempts']==count
    page.goto(base+'?view=revision');expect(page.locator('.ls-block-recall')).to_have_count(12)
    page.locator('.ls-remembered[data-response="revisit"]').nth(5).click();expect(page.locator('.ls-block-recall').nth(5).locator('.ls-engagement-status')).to_contain_text('Self-report saved')
    page.goto(base+'?view=revision&section=lesson-20&budget=5');expect(page.locator('.ls-block-recall')).to_have_count(4);expect(page.locator('.ls-block-recall').first).to_contain_text('distinction 6');expect(page.locator('.ls-recheck-queue')).to_contain_text('q31')
    page.goto(base+'?view=revision&budget=15');expect(page.locator('.ls-block-recall')).to_have_count(12)
    page.goto(base+'?view=revision&budget=full');expect(page.locator('.ls-block-teaching')).to_contain_text('list members 20');expect(page.locator('.ls-block-recall')).to_have_count(12)
    page.emulate_media(media='print');assert not page.locator('#app-sidebar').is_visible();expect(page.locator('.ls-block-teaching')).to_contain_text('list members 20');page.emulate_media(media='screen')
    page.click('#ls-focus');expect(page.locator('#app-sidebar')).not_to_be_visible();page.click('#ls-contents');page.keyboard.press('Escape');expect(page.locator('#ls-focus')).to_have_text('Exit focus');page.keyboard.press('Escape');expect(page.locator('#ls-focus')).to_have_text('Focus Reading')
    no_overflow(page);screenshot(page,f'v13-exam-full-{width}.png');page.close()


def test_review_filters_exact_element_storage_denial_offline_and_fullscreen(browser,quality_live):
    from playwright.sync_api import expect
    url,s,p=quality_live;context=browser.new_context(viewport={'width':1366,'height':900});page=context.new_page();base=url+'/learning/modules/synthetic/1'
    page.add_init_script('for (const k of ["localStorage","sessionStorage"])Object.defineProperty(window,k,{get(){throw new Error("denied")}})')
    page.goto(base+'/coverage?page=13&issue=synthetic-issue&state=unresolved');expect(page.locator('.ls-ledger-entry')).not_to_have_count(0)
    page.locator('.ls-ledger-entry summary').first.click();page.get_by_role('link',name='Inspect exact source element',exact=True).first.click();expect(page.get_by_role('heading',name='Selected source element',exact=False)).to_be_visible();expect(page.locator('.ls-source-page')).to_have_count(1)
    page.select_option('#ls-source-zoom','150');no_overflow(page)
    page.goto(base+'?view=learn&section=lesson-13');page.click('#ls-fullscreen');expect(page.locator('#ls-focus')).to_have_text('Exit focus')
    page.wait_for_function('document.fullscreenElement!==null||document.querySelector("#ls-control-status").textContent.includes("unavailable")')
    if page.evaluate('!!document.fullscreenElement'):
        page.evaluate('document.exitFullscreen()');expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    page.keyboard.press('Escape');context.set_offline(True);page.locator('.ls-teachback-input').fill('Retain this offline response.');page.locator('.ls-save-teachback').click();expect(page.locator('.ls-teachback-status')).to_contain_text('not saved');assert page.locator('.ls-teachback-input').input_value()=='Retain this offline response.'
    context.set_offline(False);page.close();context.close()


def test_visualise_sidebar_subsection_targets_are_rendered(browser,quality_live):
    url,s,p=quality_live;page=browser.new_page(viewport={'width':1366,'height':900});page.goto(url+'/learning/modules/synthetic/1?view=visualise&section=lesson-13')
    links=page.locator('.ls-subsections a');assert links.count()==3
    for link in links.all():assert page.locator(link.get_attribute('href')).count()==1
    page.close()
