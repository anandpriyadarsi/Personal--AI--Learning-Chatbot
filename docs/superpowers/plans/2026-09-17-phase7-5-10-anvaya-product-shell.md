# Phase 7.5.10 ANVAYA Product Shell + Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic Phase 7.5 browser chrome with the approved dark-first ANVAYA product shell and brand identity while preserving every existing route, academic service boundary, persistence rule, and page behaviour.

**Architecture:** Phase 7.5.10 is presentation-only. Keep all existing Flask routes and application services unchanged; rebuild only the shared Jinja shell and local static assets, add a tiny dependency-free mobile-navigation script, and restyle the existing page vocabulary through shared CSS tokens/primitives. Future workspaces that do not yet have real routes are shown only as disabled navigation destinations so the shell communicates the approved information architecture without inventing functionality.

**Tech Stack:** Python 3.8-compatible project, Flask 3.1.2, Jinja2, semantic HTML, local CSS, dependency-free browser JavaScript, pytest, PowerShell gate scripts, user-supplied PNG brand assets.

**Spec:** `docs/superpowers/specs/2026-09-17-anvaya-operational-dashboard-design.md`

## Global Constraints

- Continue on branch `phase7/deprecation-observation` from the commit containing this plan; verify the exact HEAD before any implementation edit.
- The approved design commit immediately before this plan is `f2ccfa1854b6b7f6ad6b6b1304ed121820cc0740`; do not restart or rewrite Phase 7.1-7.5.9.
- Do not modify `main`.
- Phase 7.5.10 is presentation-focused. Do not add note/resource/task/assessment/calendar/planning write capability in this phase.
- Do not modify Flask route semantics, application services, repositories, migrations, SQLite schema, authority routing, tutor/retrieval logic, or production academic data.
- Existing real routes remain real routes: Home, Tutor (`/agent`), Notes, Resources, Knowledge, Courses, Assessments, Calendar, and Planning.
- Approved future destinations without a real route in the current branch — Obsidian, Progress, Grades, and Settings — must be visible only as disabled/non-link navigation items. Do not invent stub routes and do not fake successful capability/status states.
- Use visible identity `ANVAYA` with descriptor `Personal Learning Intelligence`; do not rename stable internal Python packages/classes/database objects for branding.
- Brand colours are normative: Primary Dark `#0B0F14`, Primary Light `#E8EDF2`, Accent Teal `#55C2B8`, Supporting Blue-Gray `#64748B`.
- The interface is dark-first; do not restore a light-first default through `prefers-color-scheme`.
- Use the supplied ANVAYA assets locally. No CDN fonts, remote icon packs, external scripts, remote images, or network-dependent UI assets.
- The transparent ANVAYA wordmark is the desktop-sidebar identity; the symbol-only mark is the favicon/mobile mark. README/banner/splash/brand-guide artwork belongs under `docs/brand/`, not ordinary dashboard content.
- Do not distort, recolour, rotate, glow, or add heavy effects to supplied logo artwork.
- Accessibility requirements: visible keyboard focus, semantic navigation, `aria-current` on the active destination, keyboard-operable mobile navigation, readable contrast, status not communicated by colour alone, reduced-motion-safe transitions, and no normal-workflow horizontal scrolling on mobile.
- No implementation commit until the complete `phase7_5_fix10_gate.ps1` gate is green. Keep implementation work uncommitted until the final task, then make one scoped implementation commit.

---

## File Structure

**Create**
- `personal_learning_assistant/ui/web/static/brand/anvaya-mark.png` — byte-for-byte copy of supplied symbol-only transparent ANVAYA mark (`ChatGPT Image Sep 17, 2026, 02_32_00 PM (4).png`).
- `personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png` — byte-for-byte copy of supplied transparent white ANVAYA wordmark/tagline (`ChatGPT Image Sep 17, 2026, 02_32_00 PM (1).png`).
- `personal_learning_assistant/ui/web/static/js/app.js` — mobile navigation only; no data writes, network calls, local storage, or academic logic.
- `tests/test_phase7_5_anvaya_shell.py` — focused shell/asset/navigation/accessibility/regression tests.
- `docs/brand/ANVAYA_PRIMARY_LIGHT.png` — supplied light-background primary logo (`ChatGPT Image Sep 17, 2026, 02_32_00 PM (3)(1).png`).
- `docs/brand/ANVAYA_README_BANNER.png` — supplied dark README/banner artwork (`ChatGPT Image Sep 17, 2026, 02_32_00 PM (5).png`).
- `docs/brand/ANVAYA_SPLASH.png` — supplied splash artwork (`ChatGPT Image Sep 17, 2026, 02_32_00 PM (6).png`).
- `docs/brand/ANVAYA_MINI_BRAND_GUIDE.png` — supplied mini brand guide (`ChatGPT Image Sep 17, 2026, 02_32_01 PM (7).png`).
- `PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md` — implementation boundary, asset mapping, run instructions, and deferred capabilities.
- `phase7_5_fix10_gate.ps1` — focused + regression + integrity completion gate.

**Modify**
- `personal_learning_assistant/ui/web/templates/base.html` — ANVAYA shell, brand identity, grouped navigation, top bar, responsive drawer hooks, favicon, local script.
- `personal_learning_assistant/ui/web/static/css/app.css` — dark-first ANVAYA tokens, shell layout, shared primitives, existing-page compatibility, responsive/accessibility rules.
- `tests/test_phase7_5_web_foundation.py` — update the old generic product-name/navigation expectation to the approved ANVAYA identity while keeping the original foundation guarantees.

**Do not modify in Phase 7.5.10**
- `personal_learning_assistant/ui/web/routes.py`
- every existing page template other than `base.html`
- `personal_learning_assistant/services/**`
- `personal_learning_assistant/repositories/**`
- `personal_learning_assistant/tutor/**`
- `personal_learning_assistant/retrieval/**`
- migrations/schema/authority files
- `data/learning_assistant.db`
- `.phase5_retrieval/**`
- legacy JSON academic data

---

### Task 1: Lock the ANVAYA shell contract with failing tests

**Files:**
- Create: `tests/test_phase7_5_anvaya_shell.py`
- Modify: `tests/test_phase7_5_web_foundation.py`

**Interfaces:**
- Consumes: existing `create_app({"TESTING": True})`, existing route endpoint names, Flask local static serving.
- Produces: an executable contract for identity, navigation order, local assets, responsive drawer hooks, dark-first tokens, and preservation of existing GET routes.

- [ ] **Step 1: Write the new shell tests before changing production UI files**

Create `tests/test_phase7_5_anvaya_shell.py` with the following concrete checks:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "personal_learning_assistant" / "ui" / "web"


def _client():
    from personal_learning_assistant.ui.web import create_app

    return create_app({"TESTING": True}).test_client()


def test_home_renders_anvaya_identity_and_local_brand_assets():
    response = _client().get("/")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ANVAYA" in text
    assert "Personal Learning Intelligence" in text
    assert "/static/brand/anvaya-wordmark-white.png" in text
    assert "/static/brand/anvaya-mark.png" in text
    assert 'rel="icon"' in text
    assert "Personal AI Learning Assistant" not in text
    assert "https://" not in text
    assert "http://" not in text


def test_primary_navigation_follows_approved_group_order():
    source = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    markers = (
        ">Home<",
        ">ANVAYA<",
        ">Tutor<",
        ">Learning<",
        ">Notes<",
        ">Obsidian<",
        ">Resources<",
        ">Knowledge<",
        ">Academics<",
        ">Courses<",
        ">Assessments<",
        ">Calendar<",
        ">Planning<",
        ">Progress<",
        ">Grades<",
        ">System<",
        ">Settings<",
    )
    positions = [source.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_real_destinations_are_links_and_future_destinations_are_disabled():
    source = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    for endpoint in (
        "web.home",
        "web.academic_agent",
        "web.notes",
        "web.resources",
        "web.knowledge",
        "web.courses",
        "web.assessments",
        "web.calendar",
        "web.planning",
    ):
        assert "url_for('{}')".format(endpoint) in source
    for label in ("Obsidian", "Progress", "Grades", "Settings"):
        assert 'aria-disabled="true"' in source
        assert label in source
    assert "web.obsidian" not in source
    assert "web.progress" not in source
    assert "web.grades" not in source
    assert "web.settings" not in source


def test_shell_assets_are_served_locally():
    client = _client()
    for path, expected_type in (
        ("/static/css/app.css", "text/css"),
        ("/static/js/app.js", "javascript"),
        ("/static/brand/anvaya-mark.png", "image/png"),
        ("/static/brand/anvaya-wordmark-white.png", "image/png"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert expected_type in response.content_type


def test_brand_assets_are_real_png_files():
    for name in ("anvaya-mark.png", "anvaya-wordmark-white.png"):
        payload = (WEB / "static" / "brand" / name).read_bytes()
        assert payload.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(payload) > 1024


def test_css_is_dark_first_and_contains_approved_brand_tokens():
    css = (WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")
    for token in ("#0B0F14", "#E8EDF2", "#55C2B8", "#64748B", "color-scheme: dark"):
        assert token in css
    assert "prefers-color-scheme: dark" not in css
    assert "prefers-reduced-motion" in css


def test_mobile_drawer_is_keyboard_accessible_and_dependency_free():
    base = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    script = (WEB / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert 'id="nav-toggle"' in base
    assert 'aria-controls="app-sidebar"' in base
    assert 'aria-expanded="false"' in base
    assert 'id="nav-backdrop"' in base
    assert "Escape" in script
    assert "aria-expanded" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "localStorage" not in script


def test_existing_phase75_get_routes_keep_working():
    client = _client()
    for path in (
        "/",
        "/agent",
        "/notes",
        "/resources",
        "/knowledge",
        "/courses",
        "/assessments",
        "/calendar",
        "/planning",
    ):
        assert client.get(path).status_code == 200, path
```

- [ ] **Step 2: Update the old foundation identity expectation, but not its behavioural guarantees**

In `tests/test_phase7_5_web_foundation.py`, change only `test_home_route_renders_local_navigation_shell` so that it expects `ANVAYA`, `Personal Learning Intelligence`, and the currently real navigation labels (`Home`, `Tutor`, `Notes`, `Resources`, `Knowledge`, `Courses`, `Assessments`, `Calendar`, `Planning`). Keep the assertions that the rendered shell contains no `http://` or `https://` URLs.

Do not change the health-route expectation, lazy-startup test, static-CSS test, 404/500 tests, or Flask dependency test.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\test_phase7_5_anvaya_shell.py `
  tests\test_phase7_5_web_foundation.py::test_home_route_renders_local_navigation_shell
```

Expected: failures because the ANVAYA static assets, new script, new identity, grouped navigation, and dark-first brand tokens do not exist yet.

- [ ] **Step 4: Checkpoint without committing**

Run:

```powershell
git diff -- tests/test_phase7_5_anvaya_shell.py tests/test_phase7_5_web_foundation.py
```

Expected: only the new Phase 7.5.10 shell contract and the approved identity/navigation expectation change. Do not commit.

---

### Task 2: Add the approved ANVAYA asset package and dark-first design tokens

**Files:**
- Create: `personal_learning_assistant/ui/web/static/brand/anvaya-mark.png`
- Create: `personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png`
- Create: `docs/brand/ANVAYA_PRIMARY_LIGHT.png`
- Create: `docs/brand/ANVAYA_README_BANNER.png`
- Create: `docs/brand/ANVAYA_SPLASH.png`
- Create: `docs/brand/ANVAYA_MINI_BRAND_GUIDE.png`
- Modify: `personal_learning_assistant/ui/web/static/css/app.css`
- Test: `tests/test_phase7_5_anvaya_shell.py`

**Interfaces:**
- Consumes: the six approved user-supplied ANVAYA PNGs listed in File Structure.
- Produces: local static brand URLs used by `base.html` and repository-owned brand-reference assets under `docs/brand/`.

- [ ] **Step 1: Copy the supplied PNGs byte-for-byte to their exact target paths**

Create directories if needed:

```powershell
New-Item -ItemType Directory -Force personal_learning_assistant\ui\web\static\brand | Out-Null
New-Item -ItemType Directory -Force docs\brand | Out-Null
```

Then copy, without resizing/re-encoding/recolouring:

```text
symbol-only transparent mark
  -> personal_learning_assistant/ui/web/static/brand/anvaya-mark.png

transparent white ANVAYA wordmark/tagline
  -> personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png

light-background primary logo
  -> docs/brand/ANVAYA_PRIMARY_LIGHT.png

dark README/banner artwork
  -> docs/brand/ANVAYA_README_BANNER.png

splash artwork
  -> docs/brand/ANVAYA_SPLASH.png

mini brand guide
  -> docs/brand/ANVAYA_MINI_BRAND_GUIDE.png
```

Do not use the README banner, splash, or brand-guide image as ordinary dashboard decoration.

- [ ] **Step 2: Replace the light-first root variables with ANVAYA dark-first tokens**

At the start of `app.css`, use this token contract (additional derived tokens may be added, but these exact brand values must remain):

```css
:root {
  color-scheme: dark;
  --anvaya-dark: #0B0F14;
  --anvaya-light: #E8EDF2;
  --anvaya-teal: #55C2B8;
  --anvaya-blue-gray: #64748B;

  --surface-canvas: var(--anvaya-dark);
  --surface-sidebar: #0f151b;
  --surface: #131b23;
  --surface-elevated: #18232d;
  --surface-muted: #10171e;
  --text: var(--anvaya-light);
  --text-muted: #a9b4bf;
  --border: rgba(100, 116, 139, 0.34);
  --accent: var(--anvaya-teal);
  --accent-soft: rgba(85, 194, 184, 0.12);
  --focus-ring: rgba(85, 194, 184, 0.42);
  --danger: #f08a8a;
  --shadow: 0 18px 45px rgba(0, 0, 0, 0.18);

  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--text);
  background: var(--surface-canvas);
}
```

Keep fonts system-local. Do not import Inter from a CDN.

- [ ] **Step 3: Preserve existing page-class compatibility while restyling shared primitives**

Keep every existing selector used by current templates (`.hero`, `.dashboard-grid`, `.metric-card`, `.action-panel`, `.notice-panel`, `.dashboard-panel`, `.button`, `.tag`, `.score-badge`, `.error-panel`, etc.) but map them onto the ANVAYA surfaces, border, text, and accent tokens.

Add shared shell/primitives for:

```text
.app-shell
.app-sidebar
.brand-link
.brand-wordmark
.nav-section
.nav-section-label
.nav-item
.nav-status
.app-main
.topbar
.nav-toggle
.nav-backdrop
.topbar-title
.topbar-actions
.shell-status
.content
.app-footer
```

Required visual behaviour:

- desktop sidebar fixed/persistent at approximately 16-17rem;
- main workspace fills remaining width;
- cards use subtle surface contrast, not heavy glow;
- teal only for active/focus/primary emphasis;
- active navigation is identifiable by background + text/indicator, not colour alone;
- disabled destinations are visibly inactive and non-clickable;
- focus-visible outline is always visible;
- existing forms/inputs inherit dark surfaces and readable borders;
- existing tables/lists remain readable;
- long content wraps instead of creating normal-workflow horizontal scroll.

- [ ] **Step 4: Add responsive and reduced-motion rules**

At `max-width: 860px`, convert the persistent sidebar to an off-canvas drawer controlled by the body class `nav-open`; show `.nav-toggle` and `.nav-backdrop`; keep content single-column where current page rules already collapse grids.

At `max-width: 560px`, reduce content padding and make primary button/form rows wrap or stack.

Include:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

Remove the old `@media (prefers-color-scheme: dark)` override because ANVAYA is dark-first by design.

- [ ] **Step 5: Run the asset/CSS subset and verify progress**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\test_phase7_5_anvaya_shell.py::test_brand_assets_are_real_png_files `
  tests\test_phase7_5_anvaya_shell.py::test_css_is_dark_first_and_contains_approved_brand_tokens
```

Expected: PASS. The full shell test file may still fail because `base.html` and `app.js` are not yet implemented.

- [ ] **Step 6: Checkpoint without committing**

Run:

```powershell
git status --short
git diff -- personal_learning_assistant/ui/web/static/css/app.css
```

Confirm no backend/service/database file changed. Do not commit.

---

### Task 3: Build the shared ANVAYA shell and responsive navigation

**Files:**
- Modify: `personal_learning_assistant/ui/web/templates/base.html`
- Create: `personal_learning_assistant/ui/web/static/js/app.js`
- Test: `tests/test_phase7_5_anvaya_shell.py`

**Interfaces:**
- Consumes: existing `active_page` values and endpoint names from current routes.
- Produces: the shell inherited by all existing pages; no new Flask endpoint or application-service call.

- [ ] **Step 1: Replace the generic header/sidebar structure with semantic ANVAYA shell markup**

`base.html` must retain the existing `{% block title %}` and `{% block content %}` contracts, but change the default title to ANVAYA and add local brand/static assets:

```html
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0B0F14">
<title>{% block title %}ANVAYA · Personal Learning Intelligence{% endblock %}</title>
<link rel="icon" type="image/png" href="{{ url_for('static', filename='brand/anvaya-mark.png') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
<script defer src="{{ url_for('static', filename='js/app.js') }}"></script>
```

Use this structural hierarchy:

```text
skip link
.app-shell
  aside#app-sidebar.app-sidebar
    brand link -> Home
    nav[aria-label="Primary navigation"]
      Home
      ANVAYA -> Tutor
      Learning -> Notes, Obsidian(disabled), Resources, Knowledge
      Academics -> Courses, Assessments, Calendar, Planning, Progress(disabled), Grades(disabled)
      System -> Settings(disabled)
    local-first footer copy
  .app-main
    header.topbar
      mobile nav toggle
      compact mobile ANVAYA mark/name
      status text "Local workspace"
      real quick link "Ask ANVAYA" -> `/agent`
    main#main-content.content
      content block
nav backdrop for mobile drawer
```

Use the desktop transparent wordmark image inside the brand link. Keep a textual `Personal Learning Intelligence` descriptor adjacent/below it so the identity is available even if the image cannot load.

For every real navigation link, preserve the existing `active_page` contract and add `aria-current="page"` when active. For disabled items, render a `<span class="nav-item is-disabled" aria-disabled="true">` and a visible `Soon` marker; do not render `href` or `url_for()` for a route that does not exist.

Do not show the old `Phase 7.5.1` badge in the normal shell.

- [ ] **Step 2: Implement dependency-free mobile drawer behaviour in `static/js/app.js`**

Use this behaviour contract:

```javascript
(() => {
  const toggle = document.getElementById("nav-toggle");
  const sidebar = document.getElementById("app-sidebar");
  const backdrop = document.getElementById("nav-backdrop");

  if (!toggle || !sidebar || !backdrop) return;

  const setOpen = (open) => {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    backdrop.hidden = !open;
  };

  toggle.addEventListener("click", () => {
    setOpen(toggle.getAttribute("aria-expanded") !== "true");
  });

  backdrop.addEventListener("click", () => setOpen(false));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      toggle.focus();
    }
  });

  sidebar.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", () => setOpen(false));
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 860) setOpen(false);
  });
})();
```

This file must not use `fetch`, `XMLHttpRequest`, `localStorage`, remote libraries, or any academic/business logic.

- [ ] **Step 3: Run the full Phase 7.5.10 shell test file**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_phase7_5_anvaya_shell.py
```

Expected: all new shell tests PASS.

- [ ] **Step 4: Run the updated foundation tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_phase7_5_web_foundation.py
```

Expected: all foundation tests PASS, including lazy startup and error pages.

- [ ] **Step 5: Checkpoint without committing**

Run:

```powershell
git diff -- `
  personal_learning_assistant/ui/web/templates/base.html `
  personal_learning_assistant/ui/web/static/js/app.js `
  personal_learning_assistant/ui/web/static/css/app.css
```

Confirm there are no route/service changes and no remote asset URLs. Do not commit.

---

### Task 4: Prove compatibility across every existing Phase 7.5 workspace

**Files:**
- Test only: existing `tests/test_phase7_5_*.py`
- Production files: no new production file changes should be required in this task.

**Interfaces:**
- Consumes: the shell inherited by current Home/Courses/Assessments/Planning/Calendar/Notes/Resources/Knowledge/Agent pages.
- Produces: evidence that branding did not change route behaviour or academic semantics.

- [ ] **Step 1: Run all Phase 7.5 web regressions**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\test_phase7_5_web_foundation.py `
  tests\test_phase7_5_home_dashboard.py `
  tests\test_phase7_5_courses_topics.py `
  tests\test_phase7_5_assessments.py `
  tests\test_phase7_5_progress_planning.py `
  tests\test_phase7_5_calendar_grades.py `
  tests\test_phase7_5_notes_resources.py `
  tests\test_phase7_5_knowledge_rag.py `
  tests\test_phase7_5_academic_agent_web.py `
  tests\test_phase7_5_anvaya_shell.py
```

Expected: PASS. If a prior test fails only because it asserts the old visible product name/nav label, update that assertion to the approved ANVAYA wording without weakening any behavioural or safety assertion. Do not change tests that protect persistence, read-only GETs, lazy imports, tutor scope, retrieval, or service boundaries.

- [ ] **Step 2: Manually smoke-render every current workspace locally**

Run:

```powershell
.\.venv\Scripts\python.exe -m personal_learning_assistant.ui.web
```

Open `http://127.0.0.1:5000` and visit:

```text
/
/agent
/notes
/resources
/knowledge
/courses
/assessments
/calendar
/planning
```

Verify:

- desktop wordmark is clear and not oversized;
- sidebar groups match the approved hierarchy;
- disabled items cannot be clicked;
- active state is visible and includes more than colour alone;
- the top bar does not claim fake semester/course/index/Obsidian state;
- existing page data/content/forms still render;
- mobile-width layout opens/closes the drawer without horizontal page scrolling;
- `Escape` closes the drawer;
- focus ring is visible using keyboard navigation;
- no giant splash/banner/brand-guide art appears in ordinary workspaces.

Stop the server with `Ctrl+C`.

- [ ] **Step 3: Inspect scope before gate creation**

Run:

```powershell
git status --short
git diff --name-only
```

Expected production-code changes remain limited to `base.html`, `app.css`, `app.js`, and approved brand PNGs. Do not commit.

---

### Task 5: Add Phase 7.5.10 operator notes and the completion gate

**Files:**
- Create: `PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md`
- Create: `phase7_5_fix10_gate.ps1`
- Test: all Phase 7.5.10 and regression suites.

**Interfaces:**
- Consumes: all implementation files from Tasks 1-4.
- Produces: auditable completion evidence and exact local run/brand-asset guidance.

- [ ] **Step 1: Write `PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md`**

The document must state:

```text
Phase: 7.5.10 — ANVAYA Product Shell + Branding
Visible product: ANVAYA — Personal Learning Intelligence
Scope: presentation shell only
Real routes preserved: Home, Tutor, Notes, Resources, Knowledge, Courses, Assessments, Calendar, Planning
Visible but deferred: Obsidian, Progress, Grades, Settings
No new write capability
No route/service/repository/schema changes
No production academic data or retrieval-index mutation
Brand asset source-to-target mapping
How to run: python -m personal_learning_assistant.ui.web
Local URL: http://127.0.0.1:5000
Next planned phase: 7.5.11 Operational Notes + Resources
```

Also document that the README banner, splash, and mini brand guide are repository/documentation assets and are intentionally not rendered on every dashboard page.

- [ ] **Step 2: Create `phase7_5_fix10_gate.ps1` with a strict scope whitelist**

The gate must derive its expected base from the commit that introduced this plan so it cannot accidentally bless later committed implementation:

```powershell
$ExpectedBranch = "phase7/deprecation-observation"
$PlanPath = "docs/superpowers/plans/2026-09-17-phase7-5-10-anvaya-product-shell.md"
$BaseCommit = (git log -1 --format=%H -- $PlanPath).Trim()
```

Fail unless current branch equals `$ExpectedBranch` and current `HEAD` equals `$BaseCommit`.

Whitelist only:

```text
personal_learning_assistant/ui/web/templates/base.html
personal_learning_assistant/ui/web/static/css/app.css
personal_learning_assistant/ui/web/static/js/app.js
personal_learning_assistant/ui/web/static/brand/anvaya-mark.png
personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png
tests/test_phase7_5_anvaya_shell.py
tests/test_phase7_5_web_foundation.py
docs/brand/ANVAYA_PRIMARY_LIGHT.png
docs/brand/ANVAYA_README_BANNER.png
docs/brand/ANVAYA_SPLASH.png
docs/brand/ANVAYA_MINI_BRAND_GUIDE.png
PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md
phase7_5_fix10_gate.ps1
```

The gate must block any changed route, service, repository, schema/migration, production data, retrieval code/index, authority file, or existing page template other than `base.html`.

- [ ] **Step 3: Make the gate execute these ten stages**

```text
[1/10] Phase 7.5.10 focused shell tests
[2/10] Existing Phase 7.5 web regression tests (7.5.1-7.5.9)
[3/10] Route smoke test for every current GET workspace + static brand/CSS/JS assets
[4/10] Local-asset/forbidden-URL scan (no http://, https://, CDN/font/icon imports in base/CSS/JS)
[5/10] Accessibility/static shell contract scan (skip link, aria-current logic, drawer aria controls, reduced motion)
[6/10] Phase 7.1-7.4 regression tests
[7/10] Complete pytest suite using the same legacy Phase 2 deselection/rehearsal pattern as phase7_5_fix9_gate.ps1
[8/10] Python compilation + pip check + SQLite integrity/FK checks
[9/10] Protected backend/route/data/retrieval hashes and forbidden-diff verification
[10/10] Scoped git diff check + production-data/retrieval-index hash reconciliation
```

Before stage 1, hash at least:

```text
data/learning_assistant.db
.phase4_authority.json when present
data/*.json
.phase5_retrieval/**
personal_learning_assistant/ui/web/routes.py
personal_learning_assistant/services/**
personal_learning_assistant/repositories/**
personal_learning_assistant/tutor/**
personal_learning_assistant/retrieval/**
```

After stage 10, require those hashes to be unchanged.

For the forbidden-URL scan, inspect only `base.html`, `app.css`, and `app.js`; allow no literal `http://` or `https://` in those production shell files.

For static-asset checks, require every approved PNG path to exist as a non-empty file and require both app PNGs to start with the PNG signature.

The success banner must read exactly:

```text
PHASE 7.5.10 ANVAYA PRODUCT SHELL: PASS
```

and summarize that the shell/branding changed while routes, backend semantics, production academic data, and retrieval indexes remained unchanged.

- [ ] **Step 4: Run the focused gate first**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix10_gate.ps1
```

Expected: every stage green and final `PHASE 7.5.10 ANVAYA PRODUCT SHELL: PASS`.

If any stage fails, fix the underlying problem and rerun the complete gate. Do not bypass a check and do not commit.

---

### Task 6: Final review, one implementation commit, and push

**Files:**
- Review all Phase 7.5.10 allowed files.
- No additional feature work in this task.

**Interfaces:**
- Consumes: a completely green `phase7_5_fix10_gate.ps1` result.
- Produces: one auditable Phase 7.5.10 implementation commit on `phase7/deprecation-observation`.

- [ ] **Step 1: Verify the tree immediately after the green gate**

Run exactly:

```powershell
git status --short
git branch --show-current
git log --oneline -8
```

Confirm:

- branch is `phase7/deprecation-observation`;
- implementation files are still uncommitted;
- there are no out-of-scope changes;
- HEAD is still the plan commit used by the gate.

- [ ] **Step 2: Inspect the final scoped diff**

Run:

```powershell
git diff --check
git diff --stat
git diff -- `
  personal_learning_assistant/ui/web/templates/base.html `
  personal_learning_assistant/ui/web/static/css/app.css `
  personal_learning_assistant/ui/web/static/js/app.js `
  tests/test_phase7_5_anvaya_shell.py `
  tests/test_phase7_5_web_foundation.py `
  PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md `
  phase7_5_fix10_gate.ps1
```

Also verify the binary asset paths with `git status --short`.

- [ ] **Step 3: Create the single Phase 7.5.10 implementation commit**

Stage only the allowed implementation files and commit:

```powershell
git add -- `
  personal_learning_assistant/ui/web/templates/base.html `
  personal_learning_assistant/ui/web/static/css/app.css `
  personal_learning_assistant/ui/web/static/js/app.js `
  personal_learning_assistant/ui/web/static/brand/anvaya-mark.png `
  personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png `
  tests/test_phase7_5_anvaya_shell.py `
  tests/test_phase7_5_web_foundation.py `
  docs/brand/ANVAYA_PRIMARY_LIGHT.png `
  docs/brand/ANVAYA_README_BANNER.png `
  docs/brand/ANVAYA_SPLASH.png `
  docs/brand/ANVAYA_MINI_BRAND_GUIDE.png `
  PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md `
  phase7_5_fix10_gate.ps1

git commit -m "feat: add Phase 7.5.10 ANVAYA product shell"
```

- [ ] **Step 4: Verify the commit and clean tree**

Run:

```powershell
git status
git log --oneline -5
```

Expected: clean working tree with the new implementation commit at HEAD.

- [ ] **Step 5: Push the existing development branch**

Run:

```powershell
git push origin phase7/deprecation-observation
```

Do not merge to `main` as part of Phase 7.5.10.

---

## Self-Review Against the Approved Spec

- Product identity: covered by Tasks 2-3.
- Dark-first brand colours and supplied asset roles: covered by Task 2.
- Sidebar/top bar/navigation hierarchy: covered by Task 3.
- Responsive drawer/mobile behaviour: covered by Tasks 2-3.
- Accessibility/reduced motion/keyboard focus: covered by Tasks 1-3 and gate stage 5.
- Shared UI primitives and consistent existing-page presentation: covered by Task 2 without page-specific rewrites.
- Preserve existing page behaviour/backend semantics: enforced by Tasks 1, 4, 5 and the protected-diff/hash checks.
- No broad write capability: explicit global constraint and no route/service changes allowed.
- Future Obsidian/Progress/Grades/Settings destinations: visible but disabled, so the approved information architecture is represented without fake functionality.
- Local-first/no external UI dependency: enforced by focused tests and gate stage 4.
- Brand guide/banner/splash used in the correct role: repository documentation only, not ordinary working screens.
- Phase 7.5.11 remains the next functional milestone; this plan does not steal its Notes/Resources scope.

No placeholders or deferred implementation details remain inside the Phase 7.5.10 scope.