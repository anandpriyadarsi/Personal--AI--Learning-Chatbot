from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "personal_learning_assistant" / "ui" / "web"


def test_home_is_action_first_without_developer_copy():
    source = (WEB / "templates" / "home.html").read_text(encoding="utf-8")
    assert "What do you want to work on?" in source
    assert "home-command-center" in source
    assert "Open ANVAYA Tutor" in source
    assert "Ask questions, explain concepts, or continue a study conversation." in source
    assert "quick-actions" in source
    assert "Phase 7.5.2" not in source
    assert "read-only view" not in source
    assert source.index("home-command-center") < source.index("action-panel") < source.index("metric-grid")


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
    source = (WEB / "templates" / "home.html").read_text(encoding="utf-8")
    for endpoint in (
        "web.academic_agent",
        "web.notes",
        "web.resources",
        "web.assessments",
        "web.planning",
        "web.knowledge",
    ):
        assert "url_for('{}')".format(endpoint) in source
    assert "web.tasks" not in source
    assert "web.obsidian" not in source
