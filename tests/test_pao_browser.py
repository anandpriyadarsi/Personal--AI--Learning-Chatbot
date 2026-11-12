"""Real native-form and JS journeys using only disposable local sources."""
from pathlib import Path
from threading import Thread
import hashlib
import sqlite3
import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server
from tests.test_planning_analysis_v2_browser import chromium, live_hub


@pytest.mark.parametrize('width', [320,390,1366])
@pytest.mark.parametrize('javascript', [False,True])
def test_capture_partial_reload_stale_tab_and_complete(chromium, live_hub, width, javascript):
    base, state = live_hub
    context = chromium.new_context(viewport={'width':width,'height':1000},java_script_enabled=javascript)
    page = context.new_page()
    page.goto(base+'/planning/tasks')
    capture = page.locator('form[action="/planning/tasks"]')
    capture.locator('input[name=title]').fill('Practice linear algebra and write down the steps that need a further explanation')
    capture.locator('summary').click()
    capture.locator('select[name=course_id]').select_option('course-ma')
    capture.locator('input[name=estimated_minutes]').fill('30')
    capture.get_by_role('button',name='Add task',exact=True).click()
    task_id = page.url.split('#task-')[1]
    card = page.locator('#task-'+task_id)
    expect(card).to_contain_text('MA103N')
    stale = card.locator('form').filter(has=page.get_by_role('button',name='Complete',exact=True))
    stale_data = stale.locator('input').evaluate_all('(inputs)=>Object.fromEntries(inputs.map(e=>[e.name,e.value]))')
    stale_url = stale.get_attribute('action')
    card.get_by_text('Log partial progress',exact=True).click()
    progress = card.locator('form[action$="/progress"]').last
    progress.locator('input[name=actual_minutes]').fill('12')
    progress.get_by_role('button',name='Log progress',exact=True).click()
    page.reload()
    card = page.locator('#task-'+task_id)
    expect(card).to_contain_text('Recorded effort: 12 min')
    response = context.request.post(base+stale_url,form=stale_data)
    assert response.status == 409
    card.get_by_role('button',name='Complete',exact=True).click()
    page.goto(base+'/planning/tasks?status=completed')
    expect(page.locator('#task-'+task_id)).to_contain_text('Completed')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    # At 200% equivalent browser zoom, content continues in a narrow layout.
    if width == 1366:
        page.set_viewport_size({'width':683,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    context.close()


@pytest.mark.parametrize('width', [320,390,1366])
@pytest.mark.parametrize('javascript', [False,True])
def test_real_obsidian_reader_links_history_and_source_integrity(chromium,tmp_path,monkeypatch,width,javascript):
    from tests.test_pao_obsidian_identity import workspace
    from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
    from personal_learning_assistant.repositories.sqlite.obsidian_study_repository_v2 import SQLiteObsidianStudyRepositoryV2
    from personal_learning_assistant.services.obsidian_study_companion_service import ObsidianStudyCompanionService
    from personal_learning_assistant.ui.web import create_app
    monkeypatch.chdir(tmp_path)
    source = workspace(tmp_path/'vault',{'A.md':'# Matrix notes\n\n```python\n[[B]]\n```\n\n[[B#Section|Read the next note]]', 'B.md':'# B\n\n## Section\n\nNext step.'})
    source.refresh_manifest()
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'vault').glob('*.md')}
    path = tmp_path/'study.db'
    apply_migrations(path)
    companion = ObsidianStudyCompanionService(source,SQLiteObsidianStudyRepositoryV2(path))
    app = create_app({'TESTING':True,'OBSIDIAN_WORKSPACE_SERVICE_FACTORY':lambda:source,'OBSIDIAN_STUDY_SERVICE_FACTORY':lambda:companion})
    server = make_server('127.0.0.1',0,app,threaded=True)
    thread = Thread(target=server.serve_forever,daemon=True);thread.start()
    context = chromium.new_context(viewport={'width':width,'height':1000},java_script_enabled=javascript)
    try:
        page=context.new_page();base=f'http://127.0.0.1:{server.server_port}'
        assert page.goto(base+'/obsidian/note?path=A.md').status == 200
        expect(page.get_by_role('article',name='Rendered Markdown note').locator('pre')).to_contain_text('[[B]]')
        page.get_by_role('link',name='Read the next note',exact=True).click()
        assert 'B.md' in page.url and '#section' in page.url
        page.go_back()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp_path/'vault').glob('*.md')}
    finally:
        context.close();server.shutdown();thread.join();server.server_close()
