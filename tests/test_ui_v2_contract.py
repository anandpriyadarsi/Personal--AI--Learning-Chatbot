"""Meaningful server-side usability invariants for scoped workspace pages."""
from tests.ui_v2_fixtures import build_ui_fixture


def test_home_has_real_workspace_destinations_and_native_search(tmp_path):
    app = build_ui_fixture(tmp_path)['app']
    text = app.test_client().get('/').get_data(as_text=True)
    assert 'action="/knowledge"' in text and 'name="q"' in text
    assert 'ws-focus' in text
    assert 'href="/obsidian"' in text
    assert 'Provisional' in text


def test_reader_offers_progressive_focus_without_replacing_source(tmp_path):
    fixture = build_ui_fixture(tmp_path)
    before = fixture['note_path'].read_bytes()
    text = fixture['app'].test_client().get('/obsidian/note?path=Math/LU.md').get_data(as_text=True)
    assert 'data-workspace-focus' in text
    assert 'Worked example' in text
    assert fixture['note_path'].read_bytes() == before


def test_protected_pages_do_not_load_workspace_styles(tmp_path):
    app = build_ui_fixture(tmp_path)['app']
    from flask import render_template
    with app.test_request_context('/'):
        text = render_template('base.html', active_page='planning')
    assert 'workspace_v2.css' not in text
    assert 'workspace_sources.css' not in text
