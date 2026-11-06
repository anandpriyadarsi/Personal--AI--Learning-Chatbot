"""Real Flask, SQLite and Chromium. All provider replies/data are synthetic."""
import json
import os
from pathlib import Path
from threading import Thread
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.learning_studio.test_browser import browser
from tests.test_tutor_coding import coding, use, make_task, approve, ask_data

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Enable real Chromium gate')


@pytest.fixture
def coding_live(coding):
    app=coding[0]
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',coding
    finally:server.shutdown();thread.join(5);server.server_close()


def shot(page,name):
    folder=os.environ.get('ANVAYA_WEB_ARTIFACTS')
    if folder:
        Path(folder).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(folder)/name))


@pytest.mark.parametrize('width,height',[(320,568),(390,844),(768,1024),(1366,768),(1920,1080),(390,440),(1366,440)])
def test_coding_journey_and_geometry(browser,coding_live,width,height):
    base,coding=coding_live
    app,web,path,course,provider,retrieval,sid=coding
    page=browser.new_page(viewport={'width':width,'height':height})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    def separate():
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        reader=page.locator('#main-content').bounding_box();dock=page.locator('#tutor-composer').bounding_box()
        assert reader['y']+reader['height']<=dock['y']+2
        assert dock['y']+dock['height']<=height+2
        assert page.locator('#agent-question').bounding_box()['width']>=150
        assert page.locator('#main-content').evaluate('el=>el.clientHeight')>=60
    def tools():
        if page.locator('#coding-tools').is_hidden():page.locator('#coding-tools-toggle').click()
    def send(message):
        page.locator('#agent-question').fill(message)
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('#coding-status')).to_contain_text('AI feedback saved',timeout=15000)
        separate()
    try:
        page.goto(base+'/agent/sessions/'+sid)
        expect(page.get_by_role('button',name='Coding Studio',exact=True)).to_have_attribute('aria-pressed','true')
        separate();tools();separate()
        page.locator('#coding-title').fill('Pandas practice')
        page.locator('#coding-template').select_option('pandas-indexing')
        page.locator('#coding-objective').fill('Understand labelled and positional selection')
        page.locator('#coding-topic').fill('Pandas loc iloc groupby')
        page.locator('#coding-save').click()
        expect(page.locator('#coding-status')).to_contain_text('saved locally')
        assert not provider.requests
        page.locator('#coding-source-review > summary').click()
        page.locator('#coding-preview').click();expect(page.locator('#coding-consent')).to_be_enabled()
        page.locator('#coding-consent').click();expect(page.locator('#coding-status')).to_contain_text('Scope approved')
        page.locator('#coding-action').select_option('predict')
        page.locator('#coding-attempt').fill('I expect the labelled index 103 and the positional index 105')
        page.locator('#coding-code').fill('df.loc[103]\ndf.iloc[2]\n')
        page.locator('#coding-tools-close').click()
        send('Check my prediction')
        assert len(provider.requests)==1
        tools();page.locator('#coding-action').select_option('hint');page.locator('#coding-hint').select_option('2');page.locator('#coding-tools-close').click()
        send('Give me one stronger hint')
        tools();page.locator('#coding-action').select_option('debug')
        page.locator('#coding-error').fill('KeyError: 2\n<svg onload=alert(1)>')
        page.locator('#coding-code').fill('df.loc[2]')
        page.locator('#coding-save').click();expect(page.locator('#coding-status')).to_contain_text('saved locally')
        page.locator('#coding-tools-close').click();send('Why is this label missing?')
        assert len(provider.requests)==3
        assert page.locator('.coding-saved-context svg').count()==0
        expect(page.locator('.agent-turn-assistant').last).to_contain_text('AI feedback · not executed')
        tools()
        notebook_details=page.locator('#coding-tools details').filter(has=page.locator('summary',has_text='Notebook and Colab'))
        notebook_details.locator('summary').click()
        with page.expect_download() as download:page.locator('#coding-download').click()
        data=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        assert data['nbformat']==4 and all(c.get('outputs',[])==[] for c in data['cells'])
        colab=page.get_by_role('link',name='Open Colab',exact=True)
        assert colab.get_attribute('href')=='https://colab.research.google.com/' and colab.get_attribute('target')=='_blank'
        assert colab.get_attribute('rel')=='noopener noreferrer'
        assert 'ANVAYA cannot see that tab' in notebook_details.inner_text()
        page.locator('#coding-action').select_option('viva');page.locator('#coding-error').fill('Colab printed: group A 20, B 30')
        page.locator('#coding-tools-close').click();send('Ask one viva question about this result')
        page.reload();expect(page.locator('.agent-turn-assistant')).to_have_count(4)
        assert len(provider.requests)==4
        tools();expect(page.locator('#coding-code')).to_have_value('df.loc[2]')
        page.locator('#coding-code').fill('  α = "<script>"\n')
        page.locator('#coding-tools-close').click();page.locator('#agent-question').fill('Unsent draft survives a workspace toggle')
        page.get_by_role('button',name='Academic',exact=True).click()
        expect(page.locator('#coding-studio')).to_be_hidden()
        expect(page.locator('#agent-question')).to_have_value('Unsent draft survives a workspace toggle')
        page.get_by_role('button',name='Coding Studio',exact=True).click();tools()
        expect(page.locator('#coding-code')).to_have_value('  α = "<script>"\n')
        page.keyboard.press('Escape');expect(page.locator('#coding-tools')).to_be_hidden()
        expect(page.locator('#coding-tools-toggle')).to_be_focused()
        separate();assert not errors,errors
        shot(page,f'coding-{width}x{height}.png')
        # Dismiss dirty guard only when intentionally leaving after verification.
        page.on('dialog',lambda dialog:dialog.accept())
        page.goto(base+'/agent')
        page.get_by_label('Rename Synthetic Python practice').click()
        page.locator('.tutor-rename-form:visible input[name=title]').fill('Renamed Python practice')
        page.get_by_role('button',name='Save name',exact=True).click()
        expect(page.locator('.tutor-history-link',has_text='Renamed Python practice')).to_have_count(1)
        assert len(provider.requests)==4
    finally:page.close()


def test_coding_failure_retains_draft_and_replays_same_identity(browser,coding_live):
    base,coding=coding_live;sid=coding[-1]
    with use(coding) as svc:task=make_task(svc,sid);approve(svc,sid)
    original=coding[4].complete;received=[]
    def fail(request):received.append(request);raise RuntimeError('SECRET_PROVIDER_BODY')
    coding[4].complete=fail
    page=browser.new_page(viewport={'width':390,'height':844})
    requests=[]
    page.on('request',lambda r:requests.append(json.loads(r.post_data)) if r.url.endswith('/ask') and r.post_data else None)
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.locator('#coding-tools-toggle').click();page.locator('#coding-code').fill('  private_snippet = 3\n');page.locator('#coding-tools-close').click()
        page.locator('#agent-question').fill('Keep this draft on failure')
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('#coding-status')).to_contain_text('unavailable',timeout=15000)
        expect(page.locator('#agent-question')).to_have_value('Keep this draft on failure')
        assert 'SECRET_PROVIDER_BODY' not in page.content() and len(received)==1
        coding[4].complete=original
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('#coding-status')).to_contain_text('AI feedback saved',timeout=15000)
        assert requests[0]['request_id']==requests[1]['request_id']
        assert requests[1]['code']=='  private_snippet = 3\n'
    finally:page.close()


def test_safe_code_copy_and_200_percent_keyboard_layout(browser,coding_live):
    base,coding=coding_live;sid=coding[-1]
    with use(coding) as svc:
        task=make_task(svc,sid);revision=approve(svc,sid)
        svc.ask(sid,task['id'],ask_data(task,revision))
    page=browser.new_page(viewport={'width':1366,'height':768})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.evaluate("document.documentElement.style.zoom='2'")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.locator('#coding-tools-toggle').focus();page.keyboard.press('Enter')
        expect(page.locator('#coding-tools')).to_be_visible()
        page.keyboard.press('Escape');expect(page.locator('#coding-tools-toggle')).to_be_focused()
        page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(Error('denied'))},configurable:true})")
        page.locator('.tutor-markdown .coding-copy').first.click()
        expect(page.locator('.tutor-markdown .coding-copy').first).to_have_text('Select code and copy manually')
        assert page.locator('.tutor-markdown code').first.inner_text()=='α = [1, 2]\nprint(α)\n'
    finally:page.close()
