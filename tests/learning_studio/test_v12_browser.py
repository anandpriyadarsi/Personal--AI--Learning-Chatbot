import copy,os,threading
import pytest
from werkzeug.serving import make_server
from .test_browser import browser,no_overflow,screenshot
from .helpers import package,source_pdf,catalogue
from .test_service import publish
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit browser gate flag required.')

@pytest.fixture
def reader_live(tmp_path):
    raw=source_pdf(20);p=package(raw);p['source']['page_count']=20
    p['pages']=[dict(p['pages'][0],page=i) for i in range(1,21)]
    p['sections']=[dict(copy.deepcopy(p['sections'][0]),id=f'lesson-{i:02}',title=f'Lesson {i} concrete comparisons',pages=[i]) for i in range(1,21)]
    p['schema']='anvaya.learning-module.v2'
    p['sections'][11]['blocks'].append({'kind':'activity','pages':[12],'widget':'compare_reveal','prompt':'Compare these synthetic perspectives before revealing.','choices':[{'id':'a','label':'Individual perspective','detail':'Observe one record before comparing the group.'},{'id':'b','label':'Group perspective','detail':'Compare multiple records and preserve differences.'}],'feedback':'This is ungraded explanatory feedback.'})
    p['revision'].append({'kind':'recall','pages':[12],'text':'Recall the comparison','answer':'Keep individual and group views distinct.'})
    import io
    from PIL import Image
    image=io.BytesIO();Image.new('RGB',(100,150),'white').save(image,format='PNG')
    assets={f'assets/page-{i}.png':image.getvalue() for i in range(1,21)}
    for page in p['pages']:page['preview']=f"assets/page-{page['page']}.png"
    s=LearningStudioService(tmp_path/'learning_studio.sqlite3' ,source_loader=lambda _:raw,catalogue_loader=catalogue);s.stage(p,assets);s.publish(p['module_id'],1)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    server=make_server('127.0.0.1',0,app);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    yield f'http://127.0.0.1:{server.server_port}',s
    server.shutdown();t.join(10);server.server_close()

@pytest.mark.parametrize('width',[1920,1536,1366,1024,768,390,360])
def test_selected_reader_legacy_anchor_focus_and_durable_resume(browser,reader_live,width):
    from playwright.sync_api import expect
    url,s=reader_live;page=browser.new_page(viewport={'width':width,'height':864})
    page.goto(url+'/learning/modules/synthetic/1?view=learn#lesson-12')
    expect(page.locator('.ls-lesson')).to_have_count(1)
    expect(page.locator('.ls-lesson h2')).to_have_text('Lesson 12 concrete comparisons')
    expect(page.locator('#ls-reading-status')).to_contain_text('Reading position saved')
    assert s.reading_state('synthetic',1)['current']['section_id']=='lesson-12'
    page.click('#ls-focus');page.get_by_role('link',name='Next lesson',exact=True).click()
    expect(page.locator('#ls-focus')).to_have_text('Exit focus')
    expect(page.locator('.ls-lesson h2')).to_have_text('Lesson 13 concrete comparisons')
    no_overflow(page);screenshot(page,f'v12-selected-{width}.png')
    page.close()


def test_no_javascript_notes_and_source_links_remain_useful(browser,reader_live):
    url,s=reader_live;context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844});page=context.new_page()
    page.goto(url+'/learning/modules/synthetic/1?view=learn&section=lesson-12')
    assert page.locator('.ls-lesson h2').inner_text()=='Lesson 12 concrete comparisons'
    page.get_by_role('link',name='Next lesson',exact=True).click()
    assert page.locator('.ls-lesson h2').inner_text()=='Lesson 13 concrete comparisons'
    assert s.reading_state('synthetic',1)['current'] is None
    page.close();context.close()


def test_source_resume_preserves_exact_page(browser,reader_live):
    from playwright.sync_api import expect
    url,s=reader_live;page=browser.new_page(viewport={'width':390,'height':844})
    base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=source&page=12&section=lesson-12')
    expect(page.locator('#ls-reading-status')).to_contain_text('Reading position saved')
    page.goto(base)
    page.locator('#ls-resume').click()
    expect(page.locator('#source-page-12')).to_be_visible()
    assert page.locator('.ls-source-page').count()==1
    page.close()


def test_builtin_activity_recall_revisit_and_source_request_bounds(browser,reader_live):
    from playwright.sync_api import expect
    url,s=reader_live;page=browser.new_page(viewport={'width':390,'height':844});base=url+'/learning/modules/synthetic/1'
    page.goto(base+'?view=learn&section=lesson-12')
    widget=page.locator('.ls-trusted-activity');widget.locator('summary').click()
    assert not widget.locator('details').evaluate('(e)=>e.open')
    widget.locator('select').select_option('b');widget.locator('textarea').fill('Compare both views without losing differences.')
    widget.locator('summary').click();assert widget.locator('details').evaluate('(e)=>e.open')
    page.locator('.ls-save-engagement').click();expect(page.locator('.ls-engagement-status')).to_contain_text('Self-report saved')
    page.reload();expect(page.locator('.ls-trusted-activity textarea')).to_have_value('Compare both views without losing differences.')
    page.goto(base+'?view=revision&section=lesson-12')
    page.get_by_role('button',name='Revisit this card',exact=True).click();expect(page.locator('.ls-engagement-status')).to_contain_text('Self-report saved')
    page.goto(base+'?view=revision&section=lesson-13')
    expect(page.locator('.ls-engagement-status')).to_contain_text('revisit')
    requests=[];page.on('request',lambda r:requests.append(r.url))
    page.goto(base+'?view=source&page=14')
    expect(page.locator('.ls-source-page img')).to_be_visible()
    page.wait_for_function('document.querySelector(".ls-source-page img").complete')
    assert len([u for u in requests if '/assets/' in u])==1
    no_overflow(page);page.close()
