"""Real HTTP/Chromium and SQLite; the provider is explicitly SYNTHETIC."""
import json
import os
import sqlite3
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.learning_studio.test_browser import browser
from tests.test_phase7_5_academic_agent_web import (
    build_test_web_service, table_counts, open_database, FakeProvider, first_retrieval_hit,
)
from tests.test_tutor21_correctness import SequenceProvider
from personal_learning_assistant.ui.web import create_app
from tutor23_live_inspect import inspect_session

pytestmark = pytest.mark.skipif(os.environ.get('ANVAYA_BROWSER_TESTS') != '1',
                              reason='Requires real Chromium: ANVAYA_BROWSER_TESTS=1')


@pytest.fixture
def real_tutor(tmp_path):
    provider = SequenceProvider([
        'Divide the entry by the pivot. What multiplier eliminates 6 below a pivot of 2?',
        'Use the entry divided by the pivot; keep the same question.',
        '<!--ANVAYA_EVAL {"status":"correct","reason":"Correct multiplier"}-->Correct. Store that multiplier in L and return to LU.',
        'Find the multiplier that eliminates 8 below a pivot of 2.',
        '<!--ANVAYA_EVAL {"status":"incorrect","misconception":"Reversed entry and pivot"}-->Divide entry by pivot. What multiplier eliminates 4 below pivot 2?',
        '**A basis** spans the space and is linearly independent.\n\n'
        r'\(L=\begin{bmatrix}1&0&0\\3&1&0\\2&1&1\end{bmatrix}\)'
        '\n\n`x_1` stays literal. <img src=x onerror=alert(1)>\n\n'
        r'$x_1+y_2$ and $x_i+1$ and $\infty$; unsupported $\left$ stays literal.',
        'Independence removes redundant vectors; a spanning set alone may contain redundancy.',
        '<!--ANVAYA_EVAL {"status":"correct","reason":"Explains both conditions"}-->That meets this session check; it is not mastery.',
        'We can revisit the gap. Which condition is unclear?',
    ])
    service, path, course, _, retrieval = build_test_web_service(tmp_path, provider=provider)
    connection = open_database(path)
    before = table_counts(connection)
    connection.close()
    app = create_app({'TESTING': True, 'ACADEMIC_AGENT_WEB_SERVICE_FACTORY': lambda: service})
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', service, path, course, provider, before
    finally:
        server.shutdown(); thread.join(timeout=5); server.server_close()


@pytest.mark.parametrize('width', [390, 768, 1366])
def test_persisted_adaptive_journey_in_real_browser(browser, real_tutor, width):
    base, service, path, course, provider, before = real_tutor
    context = browser.new_context(viewport={'width': width, 'height': 950})
    page = context.new_page()
    errors, external = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: external.append(request.url) if not request.url.startswith(base) else None)
    def ask(text):
        page.locator('#agent-question').fill(text)
        page.get_by_role('button', name='Ask tutor', exact=True).click()
        expect(page.locator('#agent-question')).to_be_visible()
        assert page.locator('.error-panel').count() == 0
    try:
        page.goto(base + '/agent')
        assert len(provider.requests) == 0
        page.locator('#session-course').select_option(course['id'])
        page.locator('#session-mode').select_option('doubt')
        page.get_by_role('button', name='Create tutor session').click()
        session_id = page.url.rsplit('/', 1)[-1]
        first_question = "I don't understand elimination multipliers in LU factorization."
        nonce = page.locator('[name=request_id]').input_value()
        csrf = page.locator('form[action$="/ask"] [name=csrf_token]').input_value()
        ask(first_question)
        replay = context.request.post(base + f'/agent/sessions/{session_id}/ask',
            form={'question': first_question, 'request_id': nonce, 'csrf_token': csrf}, max_redirects=0)
        assert replay.status == 303
        assert len(provider.requests) == 1
        expected = 'What multiplier eliminates 6 below a pivot of 2?'
        expect(page.locator('.tutor-pending-question')).to_contain_text(expected)
        page.reload()
        state = inspect_session(path, session_id)
        assert state['current_learning_state']['pending_question'] == expected
        assert state['all_state_checks_pass']
        page.get_by_role('button', name='+ Tools', exact=True).click()
        page.get_by_role('button', name='Hint only').click()
        assert len(provider.requests) == 1  # Draft control never submits.
        page.get_by_role('button', name='Ask tutor', exact=True).click()
        expect(page.locator('.tutor-pending-question')).to_contain_text(expected)
        ask('3')
        assert inspect_session(path, session_id)['current_learning_state']['answer_status'] == 'correct'
        ask('Give me one computational practice problem on LU.')
        expect(page.locator('.tutor-pending-question')).to_contain_text('Find the multiplier')
        level = inspect_session(path, session_id)['current_learning_state']['practice_level']
        ask('0.25')
        state = inspect_session(path, session_id)['current_learning_state']
        assert state['answer_status'] == 'incorrect'
        assert state['practice_level'] == max(1, level - 1)
        ask('Now explain basis and linear independence.')
        assert page.locator('.tutor-pending-question').count() == 0
        expect(page.locator('.assessment-matrix')).to_be_visible()
        assert page.locator('.assessment-matrix-cell').count() == 9
        maths = page.locator('.tutor-markdown [data-assessment-math]')
        assert maths.nth(1).inner_text() == 'x1+y2'
        assert maths.nth(1).locator('sub').all_text_contents() == ['1', '2']
        assert maths.nth(2).locator('sub').all_text_contents() == ['i']
        assert maths.nth(3).inner_text() == '∞'
        assert maths.nth(4).inner_text() == r'\left'
        expect(page.locator('code').filter(has_text='x_1')).to_have_text('x_1')
        assert page.locator('.tutor-markdown img').count() == 0
        assert not external
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        folder = os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
        if folder:
            root = Path(folder); root.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(root / f'tutor-real-state-math-{width}.png'), full_page=True)
        ask('I understand span but why does a basis need linear independence?')
        assert inspect_session(path, session_id)['current_learning_state']['exit_check_count'] == 0
        ask('I understand it now')
        expect(page.locator('.tutor-pending-question')).to_contain_text('Exit check:')
        ask('It spans the space and has no redundant vectors.')
        state = inspect_session(path, session_id)
        assert state['session_goal']['status'] == 'likely_met'
        assert state['current_learning_state']['exit_check_count'] == 1
        ask("I still don't understand why redundancy matters.")
        state = inspect_session(path, session_id)
        assert state['session_goal']['status'] != 'likely_met'
        assert state['all_state_checks_pass']
        page.locator('.tutor-answer-details').last.evaluate('(node) => node.open = true')
        page.get_by_role('button', name='Helpful', exact=True).last.click()
        page.locator('.tutor-answer-details').last.evaluate('(node) => node.open = true')
        page.get_by_role('button', name='Helpful', exact=True).last.click()
        connection = open_database(path)
        assert connection.execute('SELECT COUNT(*) FROM tutor_feedback').fetchone()[0] == before['tutor_feedback'] + 1
        after = table_counts(connection); connection.close()
        for table, count in before.items():
            if table not in {'tutor_sessions', 'tutor_turns', 'tutor_evidence_links', 'tutor_feedback'}:
                assert after[table] == count, table
        page.locator('.tutor-answer-details').last.evaluate('(node) => node.open = true')
        form = page.locator('.tutor-turn-feedback').last
        form.locator('[name=csrf_token]').evaluate('(node) => node.value="invalid"')
        form.get_by_role('button', name='Helpful', exact=True).click()
        expect(page.locator('.error-panel')).to_contain_text('token is invalid')
        assert not errors, errors
        if folder:
            (root / f'tutor-real-state-{width}.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    finally:
        context.close()


def test_exact_source_link_and_strict_reader_handoff(browser, tmp_path):
    import hashlib
    from personal_learning_assistant.services.knowledge_reader_service import KnowledgeReaderService
    provider = FakeProvider()
    service, path, course, _, retrieval = build_test_web_service(tmp_path, provider=provider)
    connection = open_database(path)
    # The broad legacy fixture uses a placeholder hash. This reader scenario
    # supplies a genuine content hash for its disposable synthetic text.
    source = connection.execute('SELECT chunk_text FROM knowledge_chunks ORDER BY id LIMIT 1').fetchone()[0]
    connection.execute('UPDATE knowledge_documents SET content_hash=?',
                       (hashlib.sha256(source.encode('utf-8')).hexdigest(),))
    hit = first_retrieval_hit(connection); connection.close()
    retrieval.hits = (hit,)
    reader = KnowledgeReaderService(database_path=path)
    session_id = service.create_session(course_id=course['id'], mode='doubt', source_policy='source_only')
    service.ask(session_id, 'Explain this source.')
    app = create_app({'TESTING': True, 'ACADEMIC_AGENT_WEB_SERVICE_FACTORY': lambda: service,
                      'KNOWLEDGE_READER_SERVICE_FACTORY': lambda: reader})
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    page = browser.new_page(viewport={'width': 1366, 'height': 950})
    try:
        page.goto(f'http://127.0.0.1:{server.server_port}/agent/sessions/{session_id}')
        page.locator('.tutor-answer-details > summary').last.click()
        link = page.locator('.agent-turn a').filter(has_text='Cited · S1')
        expect(link).to_have_attribute('href', f'/knowledge/item/{hit.document_id}')
        link.click()
        expect(page.locator('.knowledge-reader-document')).to_be_visible()
        page.locator('form[action$="/ask"] button').first.click()
        expect(page.locator('.metric-grid')).to_contain_text('Source Only')
        assert service.session_view(page.url.rsplit('/', 1)[-1])['source_policy'] == 'source_only'
        assert provider.calls == 1  # Reader GET and handoff do not call provider.
    finally:
        page.close(); server.shutdown(); thread.join(timeout=5); server.server_close()
