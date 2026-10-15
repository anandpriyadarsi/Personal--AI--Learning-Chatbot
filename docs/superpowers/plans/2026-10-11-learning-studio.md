# Learning Studio Implementation Plan

**Goal:** Source-grounded reading and persistent low-stakes practice in the existing local Flask application.
**Architecture:** Add a lazy blueprint and bounded service backed by a dedicated SQLite derived-artifact/evidence store. Read original source identity through the existing Knowledge registry; use the existing course catalogue read model. Preserve immutable source evidence snapshots and page previews per module revision without editing original sources. Reuse base.html, app.js navigation and brand assets.
**Tech stack:** Python, SQLite, Flask/Jinja, Mistune escaped Markdown, vanilla JavaScript, pytest, Playwright.
**Spec:** learning-studio-master-instruction.md (user authorised inline execution and independent design decisions).

## Global constraints
- No production academic writes, shared DB migrations, Tutor code edits, merge, force push or automatic personal Notes.
- Original source hash and page identities verified; semantic fidelity is a separate review state.
- Keys/explanations excluded from public practice data; server grades immutable question revisions.
- Existing global navigation only; focus and contents controls belong to module.

## Review focus
- Same event replay with a changed response must conflict, not become a second attempt.
- An older module revision must remain readable and gradeable after activation of a newer version.
- ZIP paths, symlinks, compressed bombs and active markup must fail closed.
- Read-only requests on a missing store must not create a DB or directories.
- Stage-to-publish source changes and removed mappings must fail closed.

## Task 1: Safe packages and independent persistence
Files: learning_studio/{validation,archive,store,service,sources,pilot}.py; tests/learning_studio/test_service.py.
Interfaces: validate_package(package,catalogue), stage(package,source,assets), publish(module_id,revision), module(module_id,revision,public=True), attempt(module_id,payload), evidence().
- [ ] Write validation, revision, read purity and server evidence tests; run and observe missing implementation failures.
- [ ] Implement schema, bounded safe ZIP import, immutable revisions and append-only events using isolated DB migration.
- [ ] Run pytest tests/learning_studio/test_service.py; expected all pass.

## Task 2: Actual Flask reader and import journey
Files: ui/web/learning_studio.py, templates/learning_{library,module,import,analysis}.html, static/{css,js}/learning_studio.*; additive base.html and __init__.py registration.
Consumes Task 1 service; produces /learning, /learning/courses/<id>, /learning/modules/<id>/<revision>, /learning/import, /learning/analysis and guarded POST APIs.
- [ ] Write route/CSRF/source ownership/empty-state tests, observe RED, implement thin routes.
- [ ] Render source/extra explanations separately; build Learn, Visualise, Revision, Practice, Weak and Original Source views.
- [ ] Test 72 synthetic modules, filter/pagination, errors, grade/retry/reopen, source serving and GET purity.

## Task 3: Pilot demo, UI validation and read-only contract
Files: learning_studio/demo.py, tests/learning_studio/test_browser.py; evidence/schema/future/handoff docs; .github/workflows/learning-studio.yml.
- [ ] Convert supplied pilot deterministically; store only disposable demo fixtures under an explicit new directory. No runtime production mapping.
- [ ] Test all 20 pages, portable original bytes, semantic flags, tables and concept diagrams.
- [ ] Headless 1440px/390px tests assert changed width, focus/restore, Contents/Escape, fullscreen denial, logo, page links and print.
- [ ] Provide grounded evidence JSON with no grade/mastery writes; Tutor context handoff is gated because /agent accepts course only.

## Task 4: Review and handoff
- [ ] Run full pytest, compileall, DB integrity/FK, protected hashes and git diff --check.
- [ ] Independent whole-branch code review; repair important findings with RED→GREEN regressions.
- [ ] Commit tested slices, push feature branch only, verify remote HEAD, provide deterministic Windows demo commands and honest acceptance matrix.
