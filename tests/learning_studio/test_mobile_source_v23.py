"""Keep the inherited strict mobile-source overflow assertion; record layout on failure."""
import json
import os
from pathlib import Path
import pytest
from tests.learning_studio.test_browser import browser, live

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Native Chromium required.')

LAYOUT="""() => ({url:location.href, width:innerWidth, scroll:document.documentElement.scrollWidth,
 body:document.body.className, x:scrollX, ready:document.readyState,
 offenders:Array.from(document.querySelectorAll('body *')).map(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
 return {tag:e.tagName,id:e.id,cls:String(e.className),text:(e.innerText||'').slice(0,90),
 left:r.left,right:r.right,width:r.width,overflow:s.overflowX,display:s.display,position:s.position,transform:s.transform,
 minWidth:s.minWidth,font:s.fontSize};}).filter(e=>e.width>0 && e.right>innerWidth+1).slice(-35)})"""

@pytest.mark.parametrize('repeat',range(12))
def test_mobile_source_anchor_keeps_strict_document_width(browser,live,repeat):
    url,_=live
    page=browser.new_page(viewport={'width':390,'height':844})
    try:
        page.goto(url+'/learning/modules/synthetic/1?view=learn')
        page.click('#nav-toggle');page.keyboard.press('Escape')
        page.click('#ls-focus');page.click('#ls-contents');page.click('#ls-close-contents')
        page.keyboard.press('Escape')
        page.locator('.ls-source-chips a').first.click()
        assert page.locator('#source-page-1').count()==1
        state=page.evaluate(LAYOUT)
        folder=os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
        if state['scroll']>state['width']+1:
            print('MOBILE_SOURCE_LAYOUT:'+json.dumps(state),flush=True)
            if folder:
                target=Path(folder);target.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(target/f'mobile-source-overflow-{repeat}.png'),full_page=True)
                (target/f'mobile-source-overflow-{repeat}.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
            page.wait_for_timeout(500)
            print('MOBILE_SOURCE_AFTER_LAYOUT:'+json.dumps(page.evaluate(LAYOUT)),flush=True)
        assert state['scroll']<=state['width']+1,state
    finally:page.close()
