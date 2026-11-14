"""Real Flask/Chromium with synthetic providers; V2 UI and screenshot ledger."""
import os
from pathlib import Path
import pytest
from playwright.sync_api import expect
from tests.learning_studio.test_browser import browser
from tests.test_tutor_final_browser import real_tutor
from tests.test_tutor_coding_browser import coding_live
from tests.test_tutor_coding import coding

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Requires real Chromium')


def shot(page, name):
    target = os.environ.get('ANVAYA_TUTOR_UI_ARTIFACTS')
    if target:
        Path(target).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(target)/(name+'.png')))


def geometry(page):
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    reader = page.locator('#main-content').bounding_box()
    composer = page.locator('#tutor-composer').bounding_box()
    assert reader['y'] + reader['height'] <= composer['y'] + 2
    assert composer['y'] + composer['height'] <= page.viewport_size['height'] + 2
    assert page.locator('#agent-question').bounding_box()['width'] >= 150


@pytest.mark.parametrize('theme', ['dark', 'light'])
@pytest.mark.parametrize('width', [320,360,390,430,768,1024,1366])
def test_v2_matrix_and_non_generating_tools(browser, real_tutor, width, theme):
    base, service, path, course, provider, before = real_tutor
    provider.responses = ['## One step at a time\n\nDivide the entry by the pivot.\n\n'
                          r'\(L=\begin{bmatrix}1&0\\3&1\end{bmatrix}\)'
                          '\n\n```python\nmultiplier = 6 / 2\n```\n\nWhat multiplier eliminates 6 below 2?']
    sid = service.create_session(course_id=course['id'], mode='doubt', source_policy='source_first', title='Understanding LU, one step at a time')
    service.ask(sid, 'Explain LU factorization with a small example.')
    page = browser.new_page(viewport={'width':width,'height':844 if width<768 else 950})
    errors=[];external=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    def route(r):
        if not r.request.url.startswith(base): external.append(r.request.url);r.abort()
        else:r.continue_()
    page.route('**/*', route)
    try:
        page.goto(base+'/agent')
        page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
        shot(page,f'home-{theme}-{width}')
        page.goto(base+'/agent/sessions/'+sid)
        page.evaluate('(theme) => document.documentElement.dataset.theme=theme', theme)
        geometry(page)
        assert page.locator('.tutor-transcript').bounding_box()['width'] <= 781
        shot(page,f'conversation-{theme}-{width}')
        page.locator('.tutor-evidence-trigger').last.click()
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Answer 2')
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Cited in this answer')
        shot(page,f'evidence-{theme}-{width}')
        page.keyboard.press('Escape')
        expect(page.locator('.tutor-evidence-trigger').last).to_be_focused()
        if width in [360,1366]:
            page.get_by_role('button',name='Sessions',exact=True).click()
            page.locator('#tutor-session-search').fill('no matches possible')
            expect(page.locator('#tutor-search-empty')).to_be_visible()
            page.locator('#tutor-session-search').fill('understanding')
            expect(page.locator('#tutor-sessions-panel .tutor-history-item:visible')).to_have_count(1)
            shot(page,f'sessions-{theme}-{width}')
            # Native modal makes background non-interactive; Tab cycles in dialog.
            page.keyboard.press('Shift+Tab')
            assert page.evaluate('document.activeElement.closest("dialog") !== null')
            page.keyboard.press('Escape')
            page.locator('#agent-question').fill('Keep my unsent thought')
            page.locator('#tutor-tools-toggle').click()
            shot(page,f'tools-{theme}-{width}')
            page.get_by_role('button',name='Quiz me',exact=True).click()
            assert page.locator('#agent-question').input_value().startswith('Keep my unsent thought')
            assert 'Ask me one question' in page.locator('#agent-question').input_value()
            assert len(provider.requests)==1
        assert not errors,errors
        assert not external,external
    finally:page.close()


def test_old_evidence_copy_failure_and_short_viewport(browser, real_tutor):
    base, service, path, course, provider, before = real_tutor
    provider.responses=['First answer without evidence.\n\n```python\nx = 3\n```','Second answer.']
    sid=service.create_session(course_id=course['id'],source_policy='source_first')
    service.ask(sid,'First question');service.ask(sid,'Second question')
    page=browser.new_page(viewport={'width':360,'height':440},reduced_motion='reduce')
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.locator('.tutor-evidence-trigger').first.click()
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Answer 2')
        page.keyboard.press('Escape')
        page.locator('.tutor-evidence-trigger').last.click()
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Answer 4')
        page.evaluate(r'''() => {
            const math=document.createElement('span'); math.dataset.assessmentMath='1';
            math.textContent='x_1'; document.querySelector('.tutor-transcript').append(math);
            document.dispatchEvent(new Event('tutor:transcript-updated'));
        }''')
        expect(page.locator('[data-assessment-math]').last).to_have_attribute('data-math-rendered','1')
        expect(page.locator('dialog[open]')).to_have_count(0)
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Conversation updated')
        page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('denied'))}, configurable:true})")
        page.get_by_role('button',name='Copy code',exact=True).first.click()
        expect(page.get_by_role('button',name='Select code and copy manually')).to_be_visible()
        page.locator('#agent-question').fill('Long question '*100)
        geometry(page)
        shot(page,'short-360')
    finally:page.close()


@pytest.mark.parametrize('failed_js',[False,True])
def test_nojs_coding_guard_and_native_switch(browser,coding_live,failed_js):
    base,coding=coding_live
    app,web,path,course,provider,retrieval,sid=coding
    context=browser.new_context(java_script_enabled=failed_js)
    page=context.new_page()
    if failed_js:
        page.route('**/js/tutor_coding.js*',lambda route:route.fulfill(body="throw new Error('deliberate init failure')",content_type='application/javascript'))
    try:
        page.goto(base+'/agent/sessions/'+sid)
        expect(page.get_by_role('button',name='Ask tutor',exact=True)).to_be_disabled()
        page.get_by_role('button',name='Switch to Academic Tutor',exact=True).click()
        expect(page.get_by_role('button',name='Ask tutor',exact=True)).to_be_enabled()
        assert web.session_view(sid)['metadata']['coding_workspace_v1']['workspace']=='academic'
        assert not provider.requests
    finally:context.close()


@pytest.mark.parametrize('width',[360,1366])
def test_coding_primary_surface_preserves_draft(browser,coding_live,width):
    base,coding=coding_live
    app,web,path,course,provider,retrieval,sid=coding
    page=browser.new_page(viewport={'width':width,'height':900})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.locator('#coding-tools-toggle').click()
        page.locator('#main-content').evaluate('(el)=>el.scrollTop=0')
        shot(page,f'coding-overview-dark-{width}')
        page.locator('#coding-title').fill('My NumPy exercise')
        page.locator('#coding-code').fill('a = [1, 2, 3]')
        page.locator('#agent-question').fill('Keep this question')
        shot(page,f'coding-dark-{width}')
        page.evaluate("document.documentElement.dataset.theme='light'")
        shot(page,f'coding-light-{width}')
        page.locator('#coding-tools-close').click()
        expect(page.locator('#agent-question')).to_have_value('Keep this question')
        expect(page.locator('#tutor-ask-form')).to_have_attribute('data-workspace','coding')
        page.locator('#coding-tools-toggle').click()
        expect(page.locator('#coding-code')).to_have_value('a = [1, 2, 3]')
        assert len(provider.requests)==0
        ids=page.locator('[id]').evaluate_all('(nodes)=>nodes.map(n=>n.id)')
        assert len(ids)==len(set(ids))
    finally:page.close()


def test_native_academic_send_and_rename_without_js(browser,real_tutor):
    base,service,path,course,provider,before=real_tutor
    sid=service.create_session(course_id=course['id'],source_policy='source_first',title='Native flow')
    context=browser.new_context(java_script_enabled=False)
    page=context.new_page()
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.locator('#agent-question').fill('Explain the elimination multiplier.')
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.agent-turn-assistant')).to_have_count(1)
        page.locator('#tutor-learning-details > summary').click()
        page.locator('.tutor-title-details > summary').click()
        page.locator('#current-title').fill('Native renamed session')
        page.get_by_role('button',name='Save name',exact=True).click()
        assert service.session_view(sid)['title']=='Native renamed session'
        assert len(provider.requests)==1
    finally:context.close()


@pytest.mark.parametrize('width',[360,1366])
def test_truthful_states_and_distinct_answer_sources(browser,real_tutor,monkeypatch,width):
    from personal_learning_assistant.tutor.http_provider import TutorProviderRequestError
    base,service,path,course,provider,before=real_tutor
    sid=service.create_session(course_id=course['id'],source_policy='source_only',title='Source-only clarification')
    service.ask(sid,'Explain this from my source.')
    page=browser.new_page(viewport={'width':width,'height':900})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        expect(page.locator('.agent-turn-assistant')).to_contain_text('project evidence')
        assert not provider.requests
        shot(page,f'insufficient-dark-{width}')
        other=service.create_session(course_id=course['id'],source_policy='source_first',title='A very detailed long title ' * 5)
        provider.responses=['First explanation.\n\n```python\nx=1\n```','Second explanation.']
        service.ask(other,'First question');service.ask(other,'Second question')
        view=service.session_view(other)
        for index,turn in enumerate(t for t in view['turns'] if t['role']=='assistant'):
            turn['evidence']=[dict(citation_label=f'S{index+1}',document_id=f'synthetic-{index}',chunk_id='test',source_title=f'Document {index+1}',source_label='Source',historical_exact=False,citation_url='',locator_label='Exact historical location unavailable',relation_type='',retrieval_score=None)]
            turn['cited_labels']=[f'S{index+1}']
        # Deliberate projection fixture exercises distinct persisted-turn rendering,
        # without asserting that current source metadata is historical evidence.
        original=service.session_view
        monkeypatch.setattr(service,'session_view',lambda identity:view if identity==other else original(identity))
        page.goto(base+'/agent/sessions/'+other)
        page.locator('.tutor-evidence-trigger').first.click()
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Document 1')
        expect(page.locator('#tutor-evidence-content')).not_to_contain_text('Document 2')
        shot(page,f'unavailable-evidence-dark-{width}')
        page.keyboard.press('Escape')
        page.locator('.tutor-evidence-trigger').last.click()
        expect(page.locator('#tutor-evidence-content')).to_contain_text('Document 2')
        expect(page.locator('#tutor-evidence-content')).not_to_contain_text('Document 1')
        page.keyboard.press('Escape')
        def fail(request): raise TutorProviderRequestError('synthetic confidential provider error')
        provider.complete=fail
        page.locator('#agent-question').fill('Retain my question after a provider failure')
        page.get_by_role('button',name='Ask tutor',exact=True).click()
        expect(page.locator('.error-panel')).to_be_visible()
        expect(page.locator('#agent-question')).to_have_value('Retain my question after a provider failure')
        shot(page,f'error-draft-dark-{width}')
        provider.configured=False
        page.goto(base+'/agent/sessions/'+other)
        expect(page.locator('#tutor-provider-state')).to_contain_text('Not configured')
        shot(page,f'no-provider-dark-{width}')
    finally:page.close()


def test_zoom_and_resize_keep_dialog_focus_and_send_reachable(browser,real_tutor):
    base,service,path,course,provider,before=real_tutor
    sid=service.create_session(course_id=course['id'],source_policy='source_first')
    page=browser.new_page(viewport={'width':1366,'height':950})
    try:
        page.goto(base+'/agent/sessions/'+sid)
        # CSS zoom exercises magnification; narrow viewport covers browser reflow.
        page.evaluate("document.documentElement.style.zoom='2'")
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        page.get_by_role('button',name='Sessions',exact=True).click()
        page.set_viewport_size({'width':768,'height':900})
        page.keyboard.press('Tab')
        assert page.evaluate('document.activeElement.closest("dialog") !== null')
        page.keyboard.press('Escape')
        page.evaluate("document.documentElement.style.zoom='1'")
        page.set_viewport_size({'width':360,'height':440})
        page.locator('#agent-question').fill('Preserve my question across viewport changes')
        page.locator('#agent-question').focus()
        geometry(page)
    finally:page.close()


@pytest.mark.parametrize('theme',['dark','light'])
def test_rendered_composer_contrast_and_exact_copy(browser,real_tutor,theme):
    base,service,path,course,provider,before=real_tutor
    provider.responses=['```python\n  α = "<literal>"\n```']
    sid=service.create_session(course_id=course['id'],source_policy='source_first')
    service.ask(sid,'Explain this code.')
    page=browser.new_page()
    try:
        page.goto(base+'/agent/sessions/'+sid)
        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
        values=page.evaluate('''() => {
            const q=getComputedStyle(document.getElementById('agent-question'));
            const row=getComputedStyle(document.querySelector('.tutor-input-row'));
            return [q.color,row.backgroundColor,row.borderTopColor];
        }''')
        import re
        def luminance(color):
            values=[int(x)/255 for x in re.findall(r'\d+',color)[:3]]
            linear=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in values]
            return sum(x*w for x,w in zip(linear,[.2126,.7152,.0722]))
        def contrast(a,b):
            lighter,darker=sorted([luminance(a),luminance(b)],reverse=True)
            return (lighter+.05)/(darker+.05)
        assert contrast(values[0],values[1])>=4.5,values
        assert contrast(values[2],values[1])>=3,values
        code=page.locator('.tutor-transcript pre code').first.inner_text()
        page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>window.copiedExact=value},configurable:true})")
        page.get_by_role('button',name='Copy code',exact=True).click()
        expect(page.get_by_role('button',name='Copied',exact=True)).to_be_visible()
        assert page.evaluate('window.copiedExact')==code
    finally:page.close()
