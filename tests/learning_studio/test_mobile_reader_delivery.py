import os
import pytest
from .test_browser import browser,no_overflow,screenshot
from .test_v13_browser import quality_live

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit Chromium gate required')


@pytest.mark.parametrize('width,height',[(320,700),(360,780),(390,844),(412,915),(768,1024),(1366,768),(844,390)])
def test_reader_widths_fullscreen_back_rotation_and_media(browser,quality_live,width,height):
    from playwright.sync_api import expect
    url,service,_=quality_live
    page=browser.new_page(viewport={'width':width,'height':height},has_touch=True)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url+'/learning/modules/synthetic/1?view=learn&section=lesson-13')
    no_overflow(page)
    page.locator('.ls-source-peek summary').click()
    page.locator('.ls-source-peek img').click()
    expect(page.locator('#ls-media-dialog')).to_be_visible()
    page.locator('#ls-media-zoom').click()
    page.locator('#ls-media-close').click()
    page.evaluate('() => {document.documentElement.requestFullscreen=()=>Promise.reject(new Error("denied"))}')
    page.click('#ls-fullscreen')
    expect(page.locator('#ls-fullscreen')).to_have_text('Exit full view')
    page.set_viewport_size({'width':height,'height':width})
    no_overflow(page)
    page.go_back()
    expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    assert 'section=lesson-13' in page.url
    assert not page.locator('body').evaluate('(b)=>b.classList.contains("ls-focus")')
    page.set_viewport_size({'width':width,'height':height})
    page.click('#ls-fullscreen');page.keyboard.press('Escape')
    expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    no_overflow(page)
    screenshot(page,f'delivery-reader-{width}x{height}.png')
    assert not errors
    page.close()


def test_fullscreen_pending_back_and_forward_do_not_leave_ghost_modes(browser,quality_live):
    from playwright.sync_api import expect
    url,_,_=quality_live
    page=browser.new_page(viewport={'width':390,'height':844})
    page.goto(url+'/learning/modules/synthetic/1?view=learn&section=lesson-13')
    page.evaluate('() => {document.documentElement.requestFullscreen=()=>new Promise((resolve,reject)=>{window.rejectFull=reject})}')
    page.click('#ls-fullscreen');page.go_back()
    page.evaluate('window.rejectFull(new Error("late denial"))')
    expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    assert not page.locator('body').evaluate('(b)=>b.classList.contains("ls-focus")')
    page.go_forward()
    expect(page.locator('#ls-fullscreen')).to_have_text('Exit full view')
    assert page.locator('body').evaluate('(b)=>b.classList.contains("ls-focus")')
    page.click('#ls-fullscreen');expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    page.evaluate('() => {document.documentElement.requestFullscreen=()=>Promise.reject(new Error("denied"))}')
    page.click('#ls-fullscreen');expect(page.locator('#ls-fullscreen')).to_have_text('Exit full view')
    page.click('#ls-fullscreen');expect(page.locator('#ls-fullscreen')).to_have_text('Fullscreen')
    page.close()
