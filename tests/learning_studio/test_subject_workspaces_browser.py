"""Real Chromium subject-workspace navigation at phone, tablet, and desktop widths."""
import os
import threading

import pytest
from werkzeug.serving import make_server
from .helpers import catalogue, source_pdf, package
from .test_browser import browser, no_overflow, screenshot
from .test_service import publish
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.ui.web import create_app

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',
    reason='Explicit Chromium browser gate required.')


@pytest.fixture
def chemistry_live(tmp_path):
    cat=catalogue()
    cat['courses'][0].update(code='CY100N',name='Green Chemistry')
    cat['courses'][1].update(code='MA103N',name='Linear Algebra')
    s=LearningStudioService(tmp_path/'learning_studio.sqlite3',
        source_loader=lambda _:source_pdf(),catalogue_loader=lambda:cat)
    p=package(mapped=True)
    p.update(module_id='chem-lesson',title='Introduction to AAS Spectroscopy')
    publish(s,p)
    app=create_app({'TESTING':True,'LEARNING_STUDIO_SERVICE_FACTORY':lambda:s})
    server=make_server('127.0.0.1',0,app)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    yield f'http://127.0.0.1:{server.server_port}',s
    server.shutdown();t.join(timeout=10);server.server_close()


@pytest.mark.parametrize('width',[390,768,1366])
def test_subject_to_chemistry_spectroscopy_to_source(browser,chemistry_live,width):
    from playwright.sync_api import expect
    url,s=chemistry_live
    page=browser.new_page(viewport={'width':width,'height':900})
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.goto(url+'/learning')
    expect(page.locator('.ls-subject-card').filter(has_text='Chemistry')).to_have_count(1)
    page.locator('.ls-subject-card').filter(has_text='Chemistry').click()
    expect(page.get_by_role('heading',name='Chemistry',exact=True)).to_be_visible()
    expect(page.locator('.ls-chemistry-track')).to_have_count(3)
    no_overflow(page)
    screenshot(page,f'chemistry-subject-hub-{width}.png')
    page.locator('.ls-chemistry-track').filter(has_text='Spectroscopy').click()
    assert 'section=spectroscopy' in page.url
    expect(page.locator('.ls-study-template')).to_contain_text('instrument')
    page.locator('.ls-learning-module').first.click()
    expect(page.locator('.ls-module-header')).to_contain_text('AAS Spectroscopy')
    no_overflow(page)
    assert not errors
    page.close()


def test_empty_chemistry_lab_template_without_javascript(browser,chemistry_live):
    from playwright.sync_api import expect
    url,_=chemistry_live
    context=browser.new_context(java_script_enabled=False,viewport={'width':390,'height':844})
    page=context.new_page()
    page.goto(url+'/learning/courses/c0?section=lab')
    expect(page.locator('.ls-study-template')).to_contain_text('Lab')
    expect(page.locator('.ls-empty-workspace')).to_contain_text('ready')
    expect(page.locator('.ls-course-quicklinks')).to_contain_text('Notes')
    no_overflow(page)
    context.close()


@pytest.mark.parametrize('width',[390,768,1024,1366,1920])
def test_compact_subject_rectangles_and_first_year_fallback(browser,chemistry_live,width):
    from playwright.sync_api import expect
    url,service=chemistry_live
    page=browser.new_page(viewport={'width':width,'height':900})
    page.goto(url+'/learning')
    heading=page.locator('.ls-subject-group .ls-section-heading h2').first
    expect(heading).to_be_visible()
    cards=page.locator('.ls-subject-card')
    expect(cards).to_have_count(6)
    # The request is for smaller landscape rectangles, not tall dashboard cards.
    for i in range(cards.count()):
        rect=cards.nth(i).bounding_box()
        assert rect is not None
        assert rect['width'] > rect['height'] * 1.35, (width,i,rect)
        assert rect['height'] < 215, (width,i,rect)
    expect(cards.first.locator('.ls-subject-summary')).to_be_visible()
    no_overflow(page)
    screenshot(page,f'compact-subject-dashboard-{width}.png')
    page.close()
