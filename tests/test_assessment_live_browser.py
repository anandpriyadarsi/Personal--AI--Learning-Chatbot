"""Optional real-browser regressions; use only synthetic temporary assessment data.

Install playwright and run `python -m playwright install chromium` to enable.
No browser mocking: the runner talks to Flask and the SQLite repository.
"""
import sqlite3
from threading import Thread

import pytest
from werkzeug.serving import make_server

from test_assessment_studio_phase_c import Clock, _app, _database, _service

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def live(tmp_path, browser, request):
    path = _database(tmp_path)
    if getattr(request, "param", None) == "practice":
        with sqlite3.connect(path) as db:
            db.execute("UPDATE assessment_runtime_specs SET mode='practice'")
            db.execute("UPDATE courses SET code='UC100N'")
    clock = Clock()
    service = _service(path, clock)
    sid = service.start("assessment-1", confirmed=True)["session_id"]
    app = _app(path, clock)
    from personal_learning_assistant.domain.tutor_models import TutorProviderResponse
    class BrowserProvider:
        def complete(self, request):
            return TutorProviderResponse("## Explanation\nUse a Boolean mask. Predict the result, then try it. <img src=x onerror=alert(1)>\n\n```python\nprint('<img src=x onerror=alert(1)>')\n```\n```output\n<img src=x onerror=alert(1)>\n```", "fixture", "fixture")
    app.config["CODING_HELPER_PROVIDER_FACTORY"] = BrowserProvider
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = browser.new_context(viewport={"width": 1366, "height": 768})
    page = context.new_page()
    base = f"http://127.0.0.1:{server.server_port}"
    yield page, base + f"/assessments/sessions/{sid}", service, sid, path, clock
    context.close()
    server.shutdown()
    thread.join()


@pytest.mark.parametrize("width,height", [(1920,1080),(1536,864),(1440,900),(1366,768),(1280,720),(1024,768),(768,768)])
@pytest.mark.parametrize("sidebar", ["0", "1"])
def test_runner_readable_with_saved_sidebar_preference(live, width, height, sidebar):
    page, url, *_ = live
    page.set_viewport_size({"width": width, "height": height})
    page.add_init_script(f"localStorage.setItem('anvaya.sidebar.collapsed', '{sidebar}')")
    page.goto(url)
    for collapsed in (False, True):
        if collapsed:
            page.locator("#assessment-palette-close").click()
        page.locator(".exam-question-text").scroll_into_view_if_needed()
        # Width should have settled after the palette's existing transition.
        page.wait_for_function("document.querySelector('.exam-question-text').getBoundingClientRect().width > 400", timeout=3000)
        box = page.locator(".exam-question-text").bounding_box()
        assert box["width"] > 400
        assert page.locator(".exam-option").first.bounding_box()["width"] > 400
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        action = page.get_by_role("button", name="Save & Next", exact=True)
        action.evaluate("element => element.scrollIntoView({block: 'center'})")
        action.click(trial=True)
        assert action.is_visible()
        assert action.bounding_box()["y"] + action.bounding_box()["height"] <= height


def test_native_form_save_update_review_previous_refresh_clear_and_final(live):
    page, url, service, sid, path, clock = live
    page.goto(url)
    deadline = service.runner_view(sid)["session"]["expires_at"]
    page.locator('input[value="B"]').check()
    page.get_by_role("button", name="Save & Next", exact=True).click()
    page.wait_for_url(url + "?q=2", timeout=5000)
    page.get_by_role("link", name="Previous", exact=True).click()
    page.wait_for_url(url + "?q=1")
    assert page.locator('input[value="B"]').is_checked()
    page.reload()
    assert page.locator('input[value="B"]').is_checked()
    page.locator('input[value="A"]').check()
    page.get_by_role("button", name="Mark for Review & Next", exact=True).click()
    page.wait_for_url(url + "?q=2")
    page.get_by_role("link", name="Previous", exact=True).click()
    page.wait_for_url(url + "?q=1")
    assert page.locator('input[value="A"]').is_checked()
    assert service.runner_view(sid, ordinal=1)["question"]["state"] == "answered_marked_for_review"
    page.get_by_role("button", name="Clear Response", exact=True).click()
    page.wait_for_function("document.querySelectorAll('input[name=option_ids]:checked').length === 0")
    page.reload()
    assert page.locator('input[name="option_ids"]:checked').count() == 0
    assert service.runner_view(sid)["session"]["expires_at"] == deadline
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM assessment_test_responses WHERE session_question_id IN (SELECT id FROM assessment_test_session_questions WHERE session_id=?)", (sid,)).fetchone()[0] == 4
    page.goto(url + "?q=4")
    page.locator("textarea").fill("My independently written explanation.")
    page.get_by_role("button", name="Save & Next", exact=True).click()
    page.wait_for_url(url + "?q=4")
    page.reload()
    assert page.locator("textarea").input_value() == "My independently written explanation."
    assert service.runner_view(sid)["session"]["status"] == "active"


def test_failed_action_retains_visible_response_and_retry_works(live):
    page, url, service, sid, *_ = live
    page.goto(url)
    page.route("**/action", lambda route: route.abort())
    page.locator('input[value="B"]').check()
    page.get_by_role("button", name="Save & Next", exact=True).click()
    playwright.expect(page.locator("#assessment-save-status")).to_contain_text("Action failed")
    assert page.locator('input[value="B"]').is_checked()
    assert page.url == url
    page.unroute("**/action")
    page.get_by_role("button", name="Save & Next", exact=True).click()
    page.wait_for_url(url + "?q=2", timeout=5000)
    assert service.runner_view(sid, ordinal=1)["question"]["response"] == {"selected_option_ids": ["B"]}


@pytest.mark.parametrize("live", ["practice"], indirect=True)
@pytest.mark.parametrize("width", [1536, 768, 390])
def test_helper_and_colab_preserve_attempt_and_are_keyboard_accessible(live, width):
    page, url, service, sid, path, clock = live
    page.set_viewport_size({"width":width,"height":864})
    page.goto(url)
    page.locator('input[value="B"]').check()
    playwright.expect(page.locator("#assessment-save-status")).to_have_text("Saved to ANVAYA")
    with sqlite3.connect(path) as db:
        before = "\n".join(db.iterdump())
    page.get_by_role("button", name="Coding Helper", exact=True).click()
    assert page.get_by_role("dialog").is_visible()
    page.locator('#coding-helper-action').select_option("concept")
    page.get_by_label("Concept / operation",exact=True).fill("Pandas filtering")
    page.get_by_role("button",name="Get help",exact=True).click()
    playwright.expect(page.locator("#coding-helper-answer")).to_contain_text("Use a Boolean mask")
    assert page.locator("#coding-helper-answer img").count() == 0
    page.locator('.coding-operations > summary').click()
    page.get_by_label("Operation category",exact=True).select_option("Pandas")
    page.get_by_label("Find an operation",exact=True).fill("groupby")
    assert page.locator(".coding-operation-card:visible").count() == 1
    assert page.get_by_role("dialog").bounding_box()["width"] <= width
    page.keyboard.press("Escape")
    assert not page.get_by_role("dialog").is_visible()
    assert page.locator("#coding-helper-open").evaluate("e => e === document.activeElement")
    assert page.locator('input[value="B"]').is_checked()
    # Stub only the external destination; the browser's real target/rel behavior remains.
    page.context.route("https://colab.research.google.com/**", lambda r: r.fulfill(body="Colab destination fixture",content_type="text/html"))
    with page.expect_popup() as popup:
        page.get_by_role("link",name="Open Google Colab",exact=False).click()
    popup.value.wait_for_load_state()
    assert popup.value.url == "https://colab.research.google.com/"
    assert popup.value.evaluate("window.opener === null")
    popup.value.close()
    assert page.url == url
    with sqlite3.connect(path) as db:
        assert "\n".join(db.iterdump()) == before
    assert page.locator('input[value="B"]').is_checked()


@pytest.mark.parametrize('live', ['practice'], indirect=True)
@pytest.mark.parametrize('width,height', [(1920,1080),(1536,864),(1366,768),(1024,768),(768,768),(390,844)])
def test_helper2_layout_modes_and_reset(live,width,height):
    page,url,service,sid,*_=live
    page.set_viewport_size({'width':width,'height':height})
    page.goto(url)
    original=page.locator('.exam-question-text').bounding_box()['width']
    page.get_by_role('button',name='Coding Helper',exact=True).click()
    assert page.locator('.exam-question-text').bounding_box()['width']==original
    assert page.locator('#coding-helper-title').bounding_box()['height'] < 60
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for mode in ['hint','concept','operation','explain_code','debug','memory','pseudocode','rebuild','viva','predict','compare','check']:
        page.locator('#coding-helper-action').select_option(mode)
        assert page.locator('#coding-mode-guidance').inner_text().strip()
    page.get_by_label('Your question',exact=True).fill('What does groupby do?')
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-answer')).to_contain_text('Boolean mask')
    page.get_by_role('button',name='Reset helper',exact=True).click()
    assert not page.locator('#coding-helper-answer-section').is_visible()
    assert page.get_by_label('Your question',exact=True).input_value()==''
    page.keyboard.press('Escape')
    assert page.locator('#coding-helper-open').evaluate('e => e === document.activeElement')
    page.get_by_role('button',name='Save & Next',exact=True).scroll_into_view_if_needed()
    page.get_by_role('button',name='Save & Next',exact=True).click(trial=True)


@pytest.mark.parametrize('course', ['MA103N','CY100N','UC103N','DE100N'])
def test_non_uc100n_has_no_tool_row_in_real_browser(live,course):
    page,url,_,_,path,*_=live
    with sqlite3.connect(path) as db: db.execute('UPDATE courses SET code=?',(course,))
    page.goto(url+'?course_code=UC100N')
    assert page.locator('.exam-tools').count()==0
    assert page.locator('#coding-helper-dialog').count()==0
    assert page.get_by_role('button',name='Save & Next',exact=True).is_visible()


@pytest.mark.parametrize('live', ['practice'], indirect=True)
def test_copy_card_context_reset_and_late_response(live):
    page,url,*_=live
    page.goto(url)
    page.get_by_role('button',name='Coding Helper',exact=True).click()
    page.locator('.coding-operations > summary').click()
    page.get_by_label('Operation category',exact=True).select_option('Pandas')
    page.get_by_label('Find an operation',exact=True).fill('groupby')
    card=page.locator('.coding-operation-card:visible')
    assert card.count()==1
    card.locator('summary').click()
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text => {window.copied=text;}}})")
    card.get_by_role('button',name='Copy syntax',exact=True).click()
    assert page.evaluate('window.copied')=="df.groupby('group')['value'].sum()"
    card.get_by_role('button',name='Learn this operation',exact=True).click()
    assert page.locator('#coding-helper-action').input_value()=='memory'
    assert page.get_by_label('Concept / operation',exact=True).input_value()=='Groupby'
    sent=[]
    page.on('request',lambda req:sent.append(req.post_data_json) if req.url.endswith('/coding-helper') else None)
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-answer-section')).to_be_visible()
    page.get_by_label('Your question',exact=True).fill('Why agg next?')
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-answer-section')).to_be_visible()
    assert sent[-1]['context_token']
    page.get_by_role('button',name='Reset helper',exact=True).click()
    page.get_by_label('Your question',exact=True).fill('New topic')
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-answer-section')).to_be_visible()
    assert sent[-1]['context_token']==''
    # Controlled slow transport ignores abort to prove the stale-result guard.
    page.evaluate("() => { window.fetch = () => new Promise(resolve => { window.releaseHelper = () => resolve({ok:true,json:async()=>({reply:'LATE REPLY',context_token:'late'})}); }); }")
    page.get_by_role('button',name='Get help',exact=True).click()
    page.get_by_role('button',name='Reset helper',exact=True).click()
    page.evaluate('window.releaseHelper()')
    assert not page.locator('#coding-helper-answer-section').is_visible()
    assert 'LATE REPLY' not in page.locator('#coding-helper-answer').inner_text()
    assert page.get_by_role('button',name='Get help',exact=True).is_enabled()


@pytest.mark.parametrize('live', ['practice'], indirect=True)
def test_helper_timeout_and_failed_copy_keep_inputs(live):
    page,url,*_=live
    page.goto(url)
    page.get_by_role('button',name='Coding Helper',exact=True).click()
    page.get_by_label('Your question',exact=True).fill('Keep my input')
    page.evaluate("() => { window.fetch = () => Promise.reject(new DOMException('test timeout', 'AbortError')); }")
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-status')).to_contain_text('timed out')
    assert page.get_by_label('Your question',exact=True).input_value()=='Keep my input'
    assert page.get_by_role('button',name='Get help',exact=True).is_enabled()
    page.locator('.coding-operations > summary').click()
    card=page.locator('.coding-operation-card').first
    card.locator('summary').click()
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('denied')}}})")
    card.get_by_role('button',name='Copy syntax',exact=True).click()
    playwright.expect(page.locator('#coding-helper-status')).to_contain_text('Select the code')


@pytest.mark.parametrize('live', ['practice'], indirect=True)
@pytest.mark.parametrize('finish', ['reset','close'])
def test_stale_error_never_overwrites_new_helper_status(live,finish):
    page,url,*_=live
    page.goto(url)
    page.get_by_role('button',name='Coding Helper',exact=True).click()
    page.get_by_label('Your question',exact=True).fill('A question')
    page.evaluate("() => { window.fetch = () => new Promise((resolve,reject) => { window.rejectHelper = () => reject(Error('Reset by upstream proxy')); }); }")
    page.get_by_role('button',name='Get help',exact=True).click()
    if finish=='reset':
        page.get_by_role('button',name='Reset helper',exact=True).click()
    else:
        page.get_by_role('button',name='Close Coding Helper',exact=True).click()
    previous=page.locator('#coding-helper-status').text_content()
    page.evaluate("async () => { window.rejectHelper(); await new Promise(resolve => setTimeout(resolve,0)); }")
    assert page.locator('#coding-helper-status').text_content()==previous
    assert not page.locator('#coding-helper-answer-section').is_visible()


@pytest.mark.parametrize('live', ['practice'], indirect=True)
def test_expired_context_notice_and_retry_clear_token(live):
    page,url,*_=live
    page.goto(url)
    page.get_by_role('button',name='Coding Helper',exact=True).click()
    page.get_by_label('Your question',exact=True).fill('A question')
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-answer-section')).to_be_visible()
    page.evaluate("() => { window.fetch = async (url,options) => { window.lastHelperPayload=JSON.parse(options.body); return {ok:false,json:async()=>({error:'Context expired; retry.',reset_context:true})}; }; }")
    page.get_by_role('button',name='Get help',exact=True).click()
    playwright.expect(page.locator('#coding-helper-status')).to_contain_text('Context expired; retry.')
    assert page.get_by_role('button',name='Get help',exact=True).is_enabled()
    page.get_by_role('button',name='Get help',exact=True).click()
    assert page.evaluate('window.lastHelperPayload.context_token')==''
