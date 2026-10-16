"""Chromium acceptance for accessible V1.6 revision queue navigation."""
import os
import pytest
from .test_browser import browser, no_overflow
from .test_v13_browser import quality_live

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',
                               reason='Explicit browser gate flag required.')


@pytest.mark.parametrize('width',[390,768,1366])
def test_complete_recheck_queue_navigation(browser,quality_live,width):
    from playwright.sync_api import expect
    url,studio,authored=quality_live
    page=browser.new_page(viewport={'width':width,'height':900})
    errors=[]
    page.on('pageerror',lambda exc:errors.append(str(exc)))
    page.goto(url+'/learning/modules/synthetic/1/quality?format=html&limit=20')
    expect(page.locator('#ls-queue-summary')).to_contain_text('Showing 1–20 of 31')
    expect(page.locator('.ls-quality-item')).to_have_count(20)
    page.get_by_role('link',name='Next questions').click()
    expect(page.locator('#ls-queue-summary')).to_contain_text('Showing 21–31 of 31')
    expect(page.locator('.ls-quality-item')).to_have_count(11)
    page.locator('#ls-queue-status').select_option('never_practised')
    page.locator('#ls-queue-page').fill('11')
    page.get_by_role('button',name='Apply filters').click()
    expect(page.locator('#ls-queue-summary')).to_contain_text('matching questions')
    assert 'status=never_practised' in page.url and 'page=11' in page.url
    assert 'offset=20' not in page.url
    assert 'correct_index' not in page.content()
    no_overflow(page)
    assert not errors
    page.close()
