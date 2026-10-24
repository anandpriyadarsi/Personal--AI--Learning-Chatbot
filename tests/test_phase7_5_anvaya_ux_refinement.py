from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "personal_learning_assistant" / "ui" / "web"


def test_home_is_action_first_without_developer_copy():
    from personal_learning_assistant.ui.web import create_app
    from tests.test_phase7_5_home_dashboard import _dashboard_fixture
    app = create_app({'TESTING': True, 'HOME_DASHBOARD_PROVIDER': _dashboard_fixture})
    text = app.test_client().get('/').get_data(as_text=True)
    main = text.split('<main', 1)[1]
    assert 'MA103N · LU Factorization' in main
    assert 'Provisional suggestion' in main
    assert main.index('MA103N · LU Factorization') < main.index('Your study spaces')
    assert 'Phase 7.5.2' not in main


def test_shell_is_compact_and_avoids_sidebar_scrollbar():
    css = (WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "grid-template-columns: 15rem minmax(0, 1fr)" in css
    assert ".app-sidebar" in css
    sidebar = css.split(".app-sidebar", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto" not in sidebar
    assert "\n  height: 100vh;" not in sidebar
    assert "width: min(9.5rem, 100%)" in css


def test_desktop_topbar_uses_workspace_language_without_implementation_subtitle():
    base = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    assert "Academic workspace" in base
    topbar_copy = base.split('<div class="topbar-copy">', 1)[1].split("</div>", 1)[0]
    assert "Local-first" not in topbar_copy
    assert "<strong>Personal Learning Intelligence</strong>" not in base


def test_sticky_topbar_has_scroll_offset_for_focused_home_content():
    css = (WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "scroll-padding-top: 4.25rem" in css


def test_home_quick_actions_only_link_to_existing_workspaces():
    from html.parser import HTMLParser
    from personal_learning_assistant.ui.web import create_app
    from tests.test_phase7_5_home_dashboard import _dashboard_fixture
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a': self.links.append(dict(attrs).get('href'))
    app = create_app({'TESTING': True, 'HOME_DASHBOARD_PROVIDER': _dashboard_fixture})
    parser = Links(); parser.feed(app.test_client().get('/').get_data(as_text=True))
    expected = {'/agent', '/notes', '/resources', '/assessments', '/planning', '/knowledge', '/obsidian', '/learning'}
    assert expected.issubset(set(parser.links))
    adapter = app.url_map.bind('localhost')
    for href in expected:
        assert adapter.match(href, method='GET')
