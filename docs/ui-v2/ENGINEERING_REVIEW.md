# UI V2 independent engineering review

Initial reviewed source: `4ddd717` against `origin/main` (`ce2e4e0`). The working tree was clean when review began. Final repair re-review covers product source `12fdef072ab95a8e5829320533ab354eed0009e8`. Review covers the changed templates, scoped styles, progressive controls, browser fixtures, and acceptance workflow. Product files were not modified by this reviewer; the reviewer added the separate protected-page smoke test requested by the implementation owner.

## Disposition

**Engineering review accepted, subject to final full-suite and hosted platform gates.** All findings E1–E7 are closed in the reviewed product source. No unresolved Critical or Important engineering defect remains from this review. No security or data-authority regression was found. This is review acceptance, not merge authorization or a claim that unobserved hosted CI has passed.

| Finding | Repair re-review disposition |
| --- | --- |
| E1 native Notes keyboard tabs | Closed: valid initial selection, roles, associations, native Tab reachability, ArrowRight selects Doubts. |
| E2 stale sidebar inertness | Closed: 390→1366 exits with `inert=false`; 1366→390 exits with the closed mobile nav inert; collapsed desktop Escape restores an operable visible nav. |
| E3 missing native focus control | Closed: native reader renders the control; Enter/Escape toggles `aria-pressed` back to false. |
| E4 no-JS navigation | Closed in scoped workspaces: native disclosure on a deep native reader navigates to Obsidian at 390px. Protected pages retain their original shell. |
| E5 protected-page browser coverage | Closed locally: 14 tests pass across seven actual protected surfaces at 390/1366. Hosted execution remains the CI gate. |
| E6 omitted native Notes fingerprint | Closed: native JSON added to before/after fingerprints; focused no-JS regression passes. |
| E7 normal-motion drawer focus | Closed: immediate visibility with transform/opacity animation, deferred focus, and a real normal-motion launcher keyboard regression. |

## Important findings

### E1 — My Notes Study Tools loses keyboard access to Doubts

Location: `personal_learning_assistant/ui/web/static/js/workspace_v2.js:23–26,42–48`, interacting with `templates/_anvaya_notes_study_tools.html:14–19`.

The new roving-tabindex code assumes an initial `aria-selected="true"`. The native My Notes markup has no `aria-selected` on either button, and its existing reader script only selects a tab when a `study_tab` query parameter exists. `syncTabs()` therefore sets **both** buttons to `tabIndex=-1` on a normal reader URL. This is a regression: the preexisting buttons were ordinary keyboard-focusable buttons.

Reproduction: open the fixture's `/notes/view/<id>`, open Study tools, then press Tab. Chromium reports both tabs as `{selected: null, tabIndex: -1, role: null}`. Focus proceeds through Close → Saved notes textarea → Save note → Analysis; neither tab can be reached, so a keyboard-only reader cannot switch to Doubts. The current companion keyboard acceptance test covers Obsidian only.

Required repair: initialize a valid selected tab before applying roving tabindex and provide native Notes tablist/tab/tabpanel associations, or preserve ordinary button tab behavior until that markup contract exists. Add a real keyboard journey on a default native reader URL, without forcibly focusing the otherwise-unreachable tab.

### E2 — Focus exit can leave a visible sidebar inert

Location: `personal_learning_assistant/ui/web/static/js/workspace_v2.js:7–12`.

Focus mode snapshots `sidebar.inert` and later restores the old value even if the shell has changed its responsive state. Existing `app.js:87–97` updates sidebar state when crossing 860px, so the saved value becomes stale.

Reproduction: open the Obsidian reader at 390×844, enter Focus reading, resize to 1366×768, and exit focus. Chromium reports `{inert: true, display: "flex", visible: true}` for `#app-sidebar`. The navigation looks available but its links cannot receive keyboard focus or normal interaction. A related conflict exists when Escape expands a previously collapsed desktop sidebar before the focus handler restores its saved inert value.

Required repair: restore inertness from the current desktop/mobile/collapsed state, with one clear owner of shell visibility, rather than a stale snapshot. Verify both breakpoint directions and the previously collapsed desktop case.

### E3 — Native reader focus acceptance is guaranteed to fail

Location: `personal_learning_assistant/ui/web/templates/anvaya_notes_reader.html:11–35`; `tests/test_ui_v2_browser.py:119–128`.

The focused browser gate parametrizes both `obsidian-reader` and `notes-reader`, then focuses `[data-workspace-focus]`. The native My Notes reader renders no such control. A real Chromium query returns a selector count of **0**. The zero-skip gate cannot pass on either hosted platform as committed.

Required repair: finish the intended native reading-focus control/layout and verify its reversible keyboard behavior. Do not report the focused workflow as passing until its complete committed parameter set executes successfully.

## Inherited acceptance gap

### E4 — Primary navigation remains unavailable without JavaScript on mobile

Location: `personal_learning_assistant/ui/web/templates/workspace_base.html:8–26`, inherited `base.html:73–75`, `static/css/app.css:262–279`.

The new workspace shell retains the JavaScript-only mobile hamburger with no native/no-script alternative. At 390×844 with JavaScript disabled, the sidebar's right edge is −8.64px and clicking Open navigation does nothing. Deep workspace pages therefore have no usable primary navigation. This predates the feature, but the explicit redesign/no-JS requirement is still unmet. The existing no-JS test verifies search and direct route visits, so it misses this case.

Required acceptance closure: provide a scoped native/no-script primary navigation fallback and exercise it on a deep reader page. Avoid changing protected-page internals to achieve this.

## Minor findings and evidence limits

### E5 — Protected-page acceptance does not exercise actual protected pages

Location: `tests/test_ui_v2_browser.py:16`; `tests/test_ui_v2_contract.py:22–29`.

The responsive list omits Planning, Analysis, Assessment, Learning Studio, and Tutor. The isolation check renders bare `base.html` with an active-page string; it proves the two new stylesheet links are absent, but cannot prove real protected templates retain controls, dark styling, and no overflow after the shared native-search change. The scoped CSS design is sound on inspection. Add or link actual mobile/desktop protected-page browser evidence before asserting the user-required shell integration gate has passed.

### E6 — Read-only fingerprint test omits the personal Notes store

Location: `tests/test_ui_v2_browser.py:145–160`; `tests/ui_v2_fixtures.py:61–68,100–102`.

The no-JS immutability test visits native Notes but fingerprints only the vault note, Obsidian SQLite database, and Resources JSON. Personal Notes live in a separate `anvaya_notes.json`, which is not checked. Include that store (and relevant asset directory metadata if claiming comprehensive Notes immutability) so the evidence matches the source-separation promise. No unintended write was observed in the reviewed implementation.

## Repair re-review finding

### E7 — Drawer open focus is attempted before its visibility transition completes

Severity: Important. Location in repair working tree: `personal_learning_assistant/ui/web/static/js/workspace_v2.js:68–73`.

With normal motion, keyboard-focus the native reader's toolbar Study tools launcher, press Enter, and wait 250ms. The drawer opens, but `document.activeElement.id` remains `notes-study-tools-launcher`; the next Tab moves through the underlying reader rather than into the selected drawer tab. The mutation observer runs its immediate `.focus()` while the transitioning drawer is not yet focusable, and never retries it. Moving the launcher into the toolbar makes the intervening document traversal substantial on a long note. The added regression currently calls `saved.focus()` manually, which bypasses the behavior under review.

Required repair: defer focus until the opened drawer is visibly focusable, and test launcher Enter/Space → selected tab focus without manually focusing that tab. Confirm close/Escape returns focus to the toolbar launcher and that reduced-motion and normal-motion modes both work.

The first repair (one `requestAnimationFrame`) was independently checked with `test_animated_drawer_open_moves_keyboard_focus`: **1 failed, 2 passed, 102 deselected** in the focused E1/E6/E7 selection. The inherited visibility transition can still be at its hidden start value in the first frame. This failure was reported back to the implementation owner for a further repair.

Final closure: scoped CSS now animates transform and opacity while visibility changes immediately. The retained animation-frame focus and the regression that opens with keyboard Enter now succeed. Independently ran the E1/E2/E3/E4/E6/E7 focused browser selection against the final product source: **7 passed, 85 deselected in 2.71s**. No tab focus was manually forced in the opening-focus regression.

## Checks performed

- Read the complete branch diff and current scoped CSS/JavaScript, shell inheritance, original reader controls, source renderer boundaries, fixture isolation, and Linux/Windows workflow.
- Ran `../venv/bin/python -m pytest -q tests/test_workspace_sources_ui.py tests/test_ui_v2_contract.py tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_15_10_notes_obsidian_separation.py`: **60 passed in 2.85s**.
- Ran fresh real Chromium against disposable fixture-backed Flask instances using `PLAYWRIGHT_BROWSERS_PATH=/workspace/scratch/a76d7b94b1bd/browsers`; reproduced E1–E4 independently of the implementation agent's full-suite/browser runs.
- Added and ran `tests/test_ui_v2_protected_browser.py`: **14 passed in 19.14s, zero skips**. Actual Planning/Analysis filters, Assessment library and active runner, Learning library and published reader, and Tutor controls render at 390/1366 with a dark canvas, one main, no page overflow/JavaScript errors, and no workspace assets. Synthetic screenshot evidence is under `../evidence/protected`; JUnit is `../evidence/protected-browser.xml`.
- Protected-page smoke is a shell regression test, not a new claim of byte-pure protected reads. Existing Assessment reads may create SQLite sidecars, and the existing Learning reader automatically POSTs reading progress. The test permits only that known progress endpoint and submits no mutation control. Those inherited behaviors were not changed.
- Inspected revised legacy UI tests and the installed-launcher fixture fix. The launcher change patches the actual activation module's stale config dependency so backup output remains disposable; original migration, backup count, academic-row equality, integrity, foreign-key, and snapshot-authority assertions remain intact. Revised Home checks validate rendered action ordering and route destinations instead of obsolete layout strings. Ran those two focused files/test selections: **6 passed in 0.45s**. The gallery's original form-free assertion was restored after native GET search became workspace-only.
- Confirmed the diff changes no product routes, services, repositories, migrations, academic schemas, or protected Planning/Analysis/Assessment/Learning/Tutor templates. Repair integration restores protected pages' original search markup; empty base extension blocks opt workspaces into native GET search and no-JS navigation.
- Confirmed all new stylesheet rules are scoped under `.workspace-v2`; protected pages do not opt into the workspace parent. New dynamic text retains Jinja escaping. Existing sanitized Markdown output paths remain intact, supported by the focused sanitizer/route tests.
- Native search preserves `GET /knowledge?q=...`. Existing explicit POST actions retain their routes, note/version identities, conflict fields, and source separation. The workflow correctly installs Chromium and rejects skipped focused browser cases; hosted platform results are outside this review's local evidence.

## Re-review requirement

The implementation owner should run the complete focused browser gate and full regression suite against the final published source and retain actual Windows/Linux workflow results. Those outcomes must be reported separately and must not be inferred from this review's 60 focused server passes, 14 protected browser passes, 6 revised-test passes, or 7 targeted repair browser passes. `git diff --check` also passed at final local re-review.
