"""Real Chromium: explicit student choice across separate synthetic evidence.

This deliberately does not certify an automatic reviewed-topic handoff. The
current task form creates a manual task; no canonical Assessment→Learning
mapping or independence claim is inferred from navigation or completion.
"""
import hashlib
import json
import hashlib
import os
from pathlib import Path
import sqlite3
from threading import Thread

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from tests.learning_studio.test_browser import browser
from tests.learning_studio.helpers import package, source_pdf
from tests.learning_studio.test_service import publish, event
from tests.test_planning_analysis_v2 import _database, NOW


def academic_inventory(path):
    # Learning explicitly saves its reading bookmark asynchronously. This
    # invariant concerns the canonical academic DB and its WAL/SHM sidecars.
    # Select canonical files before reading: an unrelated Learning SQLite
    # journal can disappear between directory enumeration and hashing.
    files = (path, path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm'))
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files if p.is_file()}


@pytest.fixture
def academic_journey(tmp_path, monkeypatch):
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    from personal_learning_assistant.services.academic_overview_service import AcademicOverviewService
    from personal_learning_assistant.services.academic_wal_snapshot import AcademicSnapshotFeed
    from personal_learning_assistant.services.assessment_evaluation_service import AssessmentEvaluationService
    from personal_learning_assistant.services.assessment_runner_service import AssessmentRunnerService
    from personal_learning_assistant.services.assessment_workspace_service import AssessmentWorkspaceService
    from personal_learning_assistant.services.operational_planner_web_service import build_operational_planner_web_service
    from personal_learning_assistant.ui.web import create_app

    monkeypatch.chdir(tmp_path)
    path = _database(tmp_path)
    catalogue = lambda: {'available': True, 'courses': [{'id': 'course-ma', 'code': 'MA103N',
        'name': 'Linear Algebra', 'topics': [{'id': 'topic-lu', 'name': 'LU Factorization'}]}]}
    learning = LearningStudioService(tmp_path / 'learning_studio.sqlite3',
        source_loader=lambda _: source_pdf(), catalogue_loader=catalogue)
    lesson = package(mapped=True)
    lesson['mapping'].update(course_id='course-ma', topic_id='topic-lu', topic_name='LU Factorization')
    publish(learning, lesson)
    learning.attempt('synthetic', event(lesson, 'prior-learning-miss'))
    # Publication belongs to this explicit fixture owner, never an Analysis GET.
    writer = sqlite3.connect(path)
    writer.execute('PRAGMA journal_mode=WAL')
    feed = AcademicSnapshotFeed(path)
    feed.publish(writer, at=NOW)
    app = create_app({'TESTING': True, 'PLANNING_LOCAL_TIMEZONE': 'UTC',
        'PLANNING_NOW': lambda: NOW.isoformat(),
        'ACADEMIC_OVERVIEW_SERVICE_FACTORY': lambda: AcademicOverviewService(path, now=lambda: NOW,
            local_timezone='UTC', wal_snapshot_provider=feed.latest, max_snapshot_age_seconds=120),
        'ASSESSMENT_RUNNER_SERVICE_FACTORY': lambda: AssessmentRunnerService(path, now_fn=lambda: NOW),
        'ASSESSMENT_EVALUATION_SERVICE_FACTORY': lambda: AssessmentEvaluationService(path),
        'ASSESSMENT_WORKSPACE_SERVICE_FACTORY': lambda: AssessmentWorkspaceService(path, now_fn=lambda: NOW),
        'OPERATIONAL_PLANNER_WEB_SERVICE_FACTORY': lambda: build_operational_planner_web_service(path),
        'LEARNING_STUDIO_SERVICE_FACTORY': lambda: learning})
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', path, learning, lesson, writer, feed
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        writer.close()


@pytest.mark.parametrize('width', [390, 768, 1366])
def test_student_manually_chooses_study_then_rechecks_exact_revision(browser, academic_journey, width):
    base, path, learning, lesson, writer, feed = academic_journey
    context = browser.new_context(viewport={'width': width, 'height': 1000})
    page = context.new_page()
    errors, external = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def local_only(route):
        if route.request.url.startswith(base + '/'):
            route.continue_()
        else:
            external.append(route.request.url)
            route.abort()
    context.route('**/*', local_only)
    try:
        response = page.goto(base + '/assessments/sessions/s1/evaluation')
        assert response.status == 200
        expect(page.locator('main')).to_contain_text('Evaluation')
        before = academic_inventory(path)
        page.goto(base + '/analysis')
        expect(page.locator('.pa-table')).to_contain_text('3 / 4')
        # Inspect the real session represented by the row, not a generic CTA.
        source = page.locator('.pa-table a[href="/assessments/sessions/s1/evaluation"]')
        expect(source).to_have_count(1)
        source.click()
        assert page.url.endswith('/assessments/sessions/s1/evaluation')
        page.goto(base + '/analysis')
        expect(page.locator('main')).to_contain_text('Candidate for manual review')
        assert academic_inventory(path) == before
        page.goto(base + '/planning/tasks')
        create = page.locator('form[action="/planning/tasks"]')
        create.locator('input[name=title]').fill('Manual choice: revise synthetic lesson revision 1')
        create.locator('input[name=estimated_minutes]').fill('30')
        create.locator('input[name=preferred_day]').fill('2026-09-28')
        create.locator('textarea[name=description]').fill(
            'Student selected after inspecting assessment s1. Learning module synthetic revision 1; '
            'source SHA256 ' + lesson['source']['sha256'] + '. No automatic cross-source mapping established.')
        create.get_by_role('button', name='Add task', exact=True).click()
        expect(page.locator('.planner-task-list')).to_contain_text('Manual choice: revise synthetic')
        page.goto(base + '/planning/day/2026-09-28')
        page.locator('input[name=start]').fill('18:00')
        page.locator('input[name=end]').fill('20:00')
        page.get_by_role('button', name='Preview available time').click()
        assert page.get_by_role('button', name='Complete', exact=True).count() == 0
        page.get_by_role('button', name='Save proposal as draft').click()
        expect(page.locator('main')).to_contain_text('18:00–20:00 · UTC')
        page.get_by_role('button', name='Approve day', exact=True).click()
        page.locator('input[name=actual_minutes]').fill('35')
        page.get_by_role('button', name='Complete', exact=True).click()
        expect(page.locator('.planner-agenda-items')).to_contain_text('recorded 35 min')
        feed.publish(writer, at=NOW)
        page.goto(base + '/analysis')
        expect(page.locator('aside[aria-labelledby=effort-title]')).to_contain_text('35 min')
        signals = page.locator('section[aria-labelledby=learning-signals-title]')
        revision = signals.get_by_role('link', name='Open revision', exact=True)
        expect(revision).to_have_attribute('href', '/learning/modules/synthetic/1?view=revision')
        revision.click()
        assert '/learning/modules/synthetic/1?view=revision' in page.url
        page.goto(base + '/analysis')
        signals.get_by_role('link', name='Recheck', exact=True).click()
        assert '/learning/modules/synthetic/1' in page.url and '#question-q1' in page.url
        expect(page.locator('.ls-question')).to_have_attribute('data-question-id', 'q1')
        page.locator('.ls-question input[type=radio][value="1"]').check()
        page.locator('.ls-question button[type=submit]').click()
        expect(page.locator('.ls-question-state')).to_contain_text('recovered needs recheck')
        page.reload()
        expect(page.locator('.ls-recheck-evidence')).to_contain_text('unverified / insufficient evidence')
        before = academic_inventory(path)
        page.goto(base + '/analysis')
        expect(signals).to_contain_text('1 recovered, needing recheck')
        expect(page.locator('aside[aria-labelledby=effort-title]')).to_contain_text('35 min')
        assert academic_inventory(path) == before
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT COUNT(*) FROM planner_tasks WHERE status="completed"').fetchone()[0] == 1
            assert db.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0] == 0
        assert not errors and not external
        folder = os.environ.get('ANVAYA_VALIDATION_ARTIFACTS')
        if folder:
            target = Path(folder)
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target / f'academic-manual-choice-{width}.png'), full_page=True)
            (target / f'academic-manual-choice-{width}.json').write_text(json.dumps({
                'viewport': width, 'fixture': 'synthetic-only', 'assessment_session': 's1',
                'learning_module': 'synthetic', 'learning_revision': 1,
                'source_sha256': lesson['source']['sha256'], 'choice': 'explicit manual task',
                'automatic_reviewed_topic_handoff': False, 'independence': 'unverified',
            }, indent=2), encoding='utf-8')
    finally:
        context.close()
