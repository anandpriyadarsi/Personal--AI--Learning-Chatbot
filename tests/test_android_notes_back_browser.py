"""Execute the exact trusted JavaScript used by Android's native Back handler."""
import json
import os
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect
from tests.test_ui_v2_protected_browser import protected_browser
from tests.test_nested_notes_browser import live

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1', reason='Real Chromium opt-in')


def native_back_script():
    source = (Path(__file__).parents[1] / 'android/app/src/main/java/in/anvaya/privateapp/MainActivity.java').read_text()
    invocation = re.search(r'target\.evaluateJavascript\((.*?), consumed ->', source, re.S).group(1)
    return ''.join(json.loads(token) for token in re.findall(r'"(?:[^"\\]|\\.)*"', invocation))


def test_native_back_closes_notes_menus_and_focus_before_navigation(protected_browser, live):
    base, _, note = live
    with protected_browser.new_context(viewport={'width':390, 'height':844}) as context:
        page = context.new_page()
        page.goto(base + '/notes')
        page.locator('#notes-create-menu>summary').click()
        assert page.evaluate(native_back_script()) is True
        expect(page.locator('#notes-create-menu')).not_to_have_attribute('open', '')
        expect(page).to_have_url(base + '/notes')
        page.goto(base + '/notes/view/' + note)
        page.locator('#notes-reader-menu>summary').click()
        assert page.evaluate(native_back_script()) is True
        expect(page.locator('#notes-reader-menu')).not_to_have_attribute('open', '')
        page.locator('#notes-reader-menu>summary').click()
        page.get_by_role('button', name='Focus Reading', exact=True).click()
        expect(page.locator('body')).to_have_class(re.compile('workspace-focus'))
        assert page.evaluate(native_back_script()) is True
        expect(page.locator('body')).not_to_have_class(re.compile('workspace-focus'))
        expect(page).to_have_url(base + '/notes/view/' + note)
        assert page.evaluate(native_back_script()) is False
