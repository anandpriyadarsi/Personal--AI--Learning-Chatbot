"""Real browser development baseline; pause/self-marking are future acceptance."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Thread

import pytest
from werkzeug.serving import make_server

from test_assessment_live_browser import browser, live, playwright
from test_assessment_studio_phase_c import Clock, _app, _database, _service


def screenshot(page, name):
    destination = os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
    if destination:
        directory = Path(destination)
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(directory / (name + '.png')), full_page=True)
        (directory / (name + '.json')).write_text(json.dumps({'url': page.url,
            'viewport': page.viewport_size, 'fixture': 'synthetic-only',
            'assertions': 'actual browser; screenshot is supporting evidence'}), encoding='utf-8')


@pytest.mark.parametrize('width', [390, 768, 1366, 1920])
def test_runner_mobile_keyboard_zoom_and_secret_boundary(live, width):
    page, url, service, sid, path, clock = live
    page.set_viewport_size({'width': width, 'height': 900})
    external = []
    def local_only(route):
        if not route.request.url.startswith(url.split('/assessments')[0] + '/'):
            external.append(route.request.url)
            route.abort()
        else:
            route.continue_()
    page.context.route('**/*', local_only)
    page.goto(url)
    assert 'SECRET-' not in page.content()
    assert page.locator('.exam-question-text').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('input[value="B"]').focus()
    assert page.locator('input[value="B"]').evaluate('el => el === document.activeElement')
    page.keyboard.press('Space')
    playwright.expect(page.locator('#assessment-save-status')).to_have_text('Saved to ANVAYA')
    assert service.runner_view(sid)['question']['response'] == {'selected_option_ids': ['B']}
    # Chromium CSS zoom exercises actual reflow and hit testing at 200%.
    page.evaluate("document.body.style.zoom = '2'")
    action = page.get_by_role('button', name='Save & Next', exact=True)
    action.scroll_into_view_if_needed()
    action.click(trial=True)
    assert page.locator('.exam-question-text').bounding_box()['width'] > 0
    screenshot(page, 'runner-' + str(width) + '-zoom200')
    assert external == []


def test_active_attempt_reopens_after_real_server_restart_with_authoritative_timer(tmp_path, browser):
    path = _database(tmp_path)
    clock = Clock()
    clock.value = datetime(2026, 10, 1, 0, 30, tzinfo=timezone.utc)
    service = _service(path, clock)
    sid = service.start('assessment-1', confirmed=True)['session_id']
    app = _app(path, clock)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = browser.new_context()
    page = context.new_page()
    url = f'http://127.0.0.1:{port}/assessments/sessions/{sid}'
    try:
        page.goto(url)
        page.locator('input[value="B"]').check()
        page.get_by_role('button', name='Save & Next', exact=True).click()
        page.wait_for_url(url + '?q=2')
        expiry = service.runner_view(sid)['session']['expires_at']
        page.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        assert not thread.is_alive()
        clock.advance(30)
        server = make_server('127.0.0.1', port, _app(path, clock), threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = context.new_page()
        page.goto(url + '?q=1')
        assert page.locator('input[value="B"]').is_checked()
        view = service.runner_view(sid)
        assert view['session']['expires_at'] == expiry
        assert view['remaining_seconds'] == 30
        playwright.expect(page.locator('#assessment-timer')).to_have_text('00:00:30')
        screenshot(page, 'active-reopen-after-server-restart')
        with sqlite3.connect(path) as db:
            before = '\n'.join(db.iterdump())
        page.goto(url.replace('/assessments/sessions/' + sid, '/static/css/app.css'))
        with sqlite3.connect(path) as db:
            assert '\n'.join(db.iterdump()) == before
    finally:
        context.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
