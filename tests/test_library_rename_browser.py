import os
from pathlib import Path
import pytest
from test_library_v2_browser import library_server
from test_learning_library_read_model import library_db

pytestmark=pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS')!='1',reason='Explicit Chromium gate required')


@pytest.mark.parametrize('width',[320,390,412,1366])
def test_rename_cancel_save_refresh_and_relationships(library_server,library_db,width):
    from playwright.sync_api import sync_playwright,expect
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={'width':width,'height':844})
        requests=[];page.on('request',lambda r:requests.append(r.method) if '/rename' in r.url else None)
        page.goto(library_server+'/library')
        first=page.locator('[data-library-rename]').first
        key=first.get_attribute('data-key')
        first.click()
        expect(page.locator('#library-rename-title')).not_to_have_value('')
        page.locator('#library-rename-title').fill('Cancelled name')
        page.click('#library-rename-cancel')
        assert not requests
        folder=os.environ.get('ANVAYA_BROWSER_ARTIFACTS')
        if folder:
            Path(folder).mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(Path(folder)/f'library-before-{width}.png'),full_page=True)
        first.click();page.locator('#library-rename-title').fill('Vedic Philosophy — Interactive Notes')
        page.click('#library-rename-save')
        expect(page.locator('#library-rename-status')).to_have_text('Document name saved.')
        expect(page.locator('[data-library-title]').filter(has_text='Vedic Philosophy — Interactive Notes')).to_have_text('Vedic Philosophy — Interactive Notes')
        page.reload()
        expect(page.locator('[data-library-title]').filter(has_text='Vedic Philosophy — Interactive Notes')).to_have_text('Vedic Philosophy — Interactive Notes')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        if folder:page.screenshot(path=str(Path(folder)/f'library-after-{width}.png'),full_page=True)
        assert requests == ['POST']
        browser.close()
