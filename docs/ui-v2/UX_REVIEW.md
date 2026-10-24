# UI V2 independent UX review

Review date: 18 October 2026. Initial source: `4ddd717` against `origin/main`; final re-review includes the U6 repair working tree based on that commit. This reviewer inspected the actual Flask/Chromium before and after PNGs under `/workspace/scratch/a76d7b94b1bd/evidence/before` and `/workspace/scratch/a76d7b94b1bd/evidence/after`, read the changed templates/CSS/JavaScript, and did not change product files. The screenshots use disposable synthetic study data, not production records.

## Judgment

The redesign is substantial. It changes information hierarchy, navigation grouping, source ownership, reading measure, search prominence, and progressive disclosure rather than merely changing colors. The charcoal/teal system is coherent and suitable for an academic workspace. Home now has one clear starting point and a recognizable agenda; vault connection management no longer dominates finding a note; Knowledge makes reading evidence the main action. The personal Notes library and vault remain explicitly separate.

The final priority-surface UX disposition is **acceptable with minor limitations**. The five Important findings below were repaired and re-reviewed; no unresolved Critical or Important UX finding remains in those surfaces. This is not unconditional release approval: the implementation owner must still satisfy the full-suite, protected-page, and hosted gates. This review does not infer production behavior, hosted CI results, screen-reader conformance, or device Safari behavior from screenshots.

## Evidence inspected

Screenshot names below are relative to `/workspace/scratch/a76d7b94b1bd/evidence`; this capture directory is outside the repository.
The after files were refreshed in place during repairs. Initial findings record issues actually observed in the earlier capture; the closure table identifies their disposition in the final images and source.

- All nine paired surfaces at 1366 and 390 pixels: Home, vault, Obsidian reader, My Notes, personal Notes reader, Knowledge results, Knowledge reader, Courses, and Resources. Both before and after images were opened and visually inspected.
- Supplemental after images: `home-320.png`, `vault-360.png`, `notes-768.png`, and `notes-reader-1024.png`.
- `workspace_base.html`, shared `base.html`, both workspace stylesheets, `workspace_v2.js`, and changed Home/vault/Notes/Knowledge/Courses/Resources templates, including form actions and source labels.
- The fixture and browser-gate source. The capture manifest records fixture HTTP 200, no document overflow, and no page errors for the paired captures. Those machine checks are not a substitute for interaction or visual assessment.
- Final re-review opened refreshed `notes-390.png`, `notes-1366.png`, `notes-reader-390.png`, `notes-reader-1366.png`, `home-390.png`, and `obsidian-reader-390.png`; read the U6 repair diff; and executed the focused closure checks recorded below.

## Independent scores

Each cell is **before → final after**, on a 1–5 scale: 1 severely impaired, 2 weak, 3 usable, 4 strong, 5 excellent with convincing evidence. Scores include the refreshed captures and repaired interactions; they are not averaged into a misleading global success number. Accessibility scores combine visible treatment and semantic code inspection, not a full assistive-technology audit.

| Priority surface | Hierarchy | Typography | Spacing | Mobile ergonomics | Actions | Consistency | Accessibility | Empty/error clarity |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Home | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4† |
| Obsidian vault | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4 | 3 → 4† |
| Obsidian reader | 3 → 4 | 3 → 4 | 3 → 4 | 2 → 4 | 3 → 4 | 3 → 4 | 2 → 4 | 3 → 3† |
| My Notes library | 3 → 4 | 3 → 4 | 2 → 4 | 3 → 3 | 3 → 4 | 2 → 4 | 3 → 4 | 2 → 4† |
| Personal Notes reader | 3 → 4 | 3 → 4 | 3 → 4 | 2 → 3 | 3 → 4 | 3 → 4 | 2 → 4 | 3 → 3† |
| Knowledge results | 2 → 4 | 3 → 4 | 2 → 4 | 2 → 4 | 2 → 4 | 3 → 4 | 2 → 4 | 2 → 4† |
| Knowledge reader | 2 → 4 | 3 → 4 | 2 → 3 | 3 → 3 | 3 → 4 | 3 → 4 | 2 → 4 | 2 → 3‡ |

† Empty/error assessment is code-only: the paired images show populated successful states. Home's unavailable Today plan message is visibly observed; no disconnected vault, empty Notes, failed search, or reader-error screenshot was provided in this set. The new Notes distinction between “No matching notes,” “No notes yet,” and “temporarily unavailable” is a real improvement in the template, but is not independently visually verified here.

‡ Empty saved-tool states are visibly observed. The no-readable-passages fallback is code-only. The Knowledge fixture contains one short passage, so the large amount of blank desktop canvas beside the tall tools rail is observed; suitability for a long multi-passage source cannot be inferred from this fixture.

My Notes mobile recovered from the initial after score of 2 to 3 following U1's repair: the first card now starts around 730px, within the 844px fixture viewport, versus around 960px in the rejected first capture. It still appears later than the approximately 620px baseline; the stronger labels and source distinction therefore do not justify claiming a net mobile-density gain. Personal reader mobile remains 3 because narrow tables and the long header stack still have the polish limitations below.

## Critical findings

None identified in the inspected visual evidence or changed UI source. This is not a claim that all runtime paths have been audited.

## Important findings from the initial review

### U1 — Mobile My Notes hides the library below a full viewport of scaffolding

Observed: `before/notes-390.png` versus `after/notes-390.png`; related after `notes-768.png`.

Reproduction: open `/notes` at 390×844 with the three fixture notes. The first card begins around 960px after the redesign, versus around 620px before. The long source explanation, stacked course/type filters, summary, and extra section heading consume the first viewport even though the library is populated. This weakens the core return-to-a-note workflow. Desktop card alignment is appreciably better.

Action: preserve the explicit personal/vault boundary in a compact native disclosure, keep find/create immediately available, and place the short course/type controls together where they remain usable. Recheck 320–390px with the first real card visible earlier; do not remove the source distinction.

Pointers: `templates/anvaya_notes_library.html`; `static/css/workspace_sources.css` source-context, toolbar, and mobile grid rules.

### U2 — Focus mode can restore stale sidebar inertness

Code-reviewed here; directly reproduced in Chromium by the independent engineering reviewer (E2 in `ENGINEERING_REVIEW.md`). At 390px enter reading focus, cross to 1366px, then exit focus. `workspace_v2.js` restores its saved mobile `sidebar.inert` value after `app.js` has recalculated desktop navigation, leaving a visible sidebar unavailable to normal interaction.

Action: derive inertness from the current navigation state and verify both breakpoint directions and initially collapsed desktop navigation. This is an interaction defect, not visible in the static before/after images.

Pointer: `static/js/workspace_v2.js`, initial `previousInert`/`setFocus` implementation.

### U3 — Personal reader focus/tab behavior is incomplete

Observed visually: `after/notes-reader-390.png` and `after/notes-reader-1366.png` have no Focus reading action, unlike the other redesigned readers. Code inspection also shows the native personal Study tools buttons lack the initial selected-tab semantics assumed by the new roving-tabindex enhancement. The engineering reviewer directly reproduced keyboard loss of the Doubts tab (E1) and the guaranteed native-reader focus-gate failure (E3).

Action: provide the intended personal reading-focus action; initialize a valid selected tab and complete tab/panel semantics without making previously focusable controls unreachable. Verify a default reader URL using ordinary keyboard navigation, rather than forcibly focusing a tab.

Pointers: `templates/anvaya_notes_reader.html`, `templates/_anvaya_notes_study_tools.html`, `static/js/workspace_v2.js`.

### U4 — Deep mobile pages still need navigation without JavaScript

Inherited acceptance gap, identified from code here and directly reproduced by the engineering reviewer (E4). The native GET search form is a good improvement, but the hamburger alone cannot expose the sidebar without JavaScript. A deep reader can therefore search or follow its back link but cannot use the full primary navigation.

Action: add a scoped native/no-script navigation fallback and check a deep reader at 390px with JavaScript disabled. Do not count direct test visits to route URLs as evidence that a user can navigate there.

Pointers: `templates/workspace_base.html`; shared `templates/base.html` navigation toggle; inherited `static/css/app.css` mobile sidebar rules.

### U5 — Hamburger appears to open invisible navigation during reading focus

Directly reproduced by this reviewer in real Chromium on the repair working tree: at 390×844 open an Obsidian reader, enter Focus reading, and click the topbar hamburger. The sidebar reports `{inert:false, display:'none'}` while the toggle reports `aria-expanded="true"`; a backdrop appears without the navigation. Focus CSS overrides the shell's attempt to open the sidebar. Static screenshots do not expose this defect.

Action: have the hamburger leave reading focus before opening navigation, or otherwise make its availability and state agree with the visible navigation. Preserve keyboard and Escape behavior. Verify both mobile and desktop activation; do not merely change the expanded label.

Pointers: `static/js/workspace_v2.js` focus controls; inherited `static/js/app.js` navigation toggle; `workspace_v2.css` `.workspace-focus .app-sidebar`.

## Minor findings and residual limitations

1. **Study tools overlap is closed.** The initial fixed bottom-right launcher intersected the table at the captured scroll position. The final screenshots place it in the reader toolbar, eliminating the overlay. Native code blocks now preserve whitespace and scroll inside their own bounds. A temporary repair capture showed document overflow; bounded native `pre` scrolling fixed it, independently verified at 390px.
2. **Narrow tables still need a stronger scrolling cue.** The final native Notes reader shows STEP broken across two lines; contained horizontal scrolling in Obsidian can hide the end of the result text. `display:block; overflow:auto` prevents document overflow but does not by itself make the hidden column obvious. Preserve table semantics, prevent wrapping of short column labels, and consider a visible scroll hint. Pointers: `workspace_v2.css` reader table rules and broad `overflow-wrap:anywhere`; `workspace_sources.css` native reader table rule. This limitation exists in the before images too. Obsidian's short column-label wrapping is repaired.
3. **The screenshot environment lacks some glyphs.** Hindi/Japanese content renders as boxes in both reader sets. This is observed in the captured Chromium environment, not a claim about every user's fonts. Supply an appropriate multilingual fallback if those scripts are supported product content. The visible Greek text remains readable. The Create note missing-glyph symptom is closed by using an ASCII plus, confirmed in the refreshed library images. Pointer: inherited `app.css` font stack.
4. **Knowledge reader metadata is spacious on mobile.** The first source passage begins around 540px in the after 390 image versus around 325px before. Focus control, title, actions, provenance and their gaps are individually clear but collectively delay reading. Tighten that stack if long-source mobile use is common. The one-passage fixture also leaves the desktop tools rail much taller than the document; a long-source screenshot remains useful follow-up evidence. Pointers: `knowledge_item.html`, reader-toolbar/header/provenance styles.
5. **Small copy remains a deliberate density compromise.** Agenda course labels are 10px, tags about 11px, and the mobile global input 12px in CSS. Their contrast is visibly better than baseline, but these are small targets for reading. Native-device zoom/text-scaling and screen-reader testing were not performed by this reviewer.
6. **Supplementary polish:** Resources displays “+ Add Resource+” in its disclosure, and the preview-style personal card retains a large plain NOTE cover. Both are inherited in the before images; they do not undermine the main hierarchy gain. Courses is calmer after disclosure, though the recorded-status explanation adds reading overhead and “1 topics” needs plural handling.

## What the redesign demonstrably improves

- **Home:** a single recommendation with an explicit existing-brief/provisional basis; obligations grouped into an agenda; workspace destinations have understandable descriptions; Analysis no longer repeats a large metric teaser. The available fixture recommendation is not presented as newly computed intelligence.
- **Vault:** a compact connection disclosure, prominent native search, linked note titles, named Open note actions, and clear relative paths. The file path/configuration machinery no longer dominates the successful state.
- **Reading:** controlled desktop measure, comfortable paragraph leading, distinctive heading levels, clear callouts, bounded tables/code, and source authority text. Personal notes retain their own Edit note identity; vault Markdown remains authoritative in the vault.
- **Knowledge:** the query and Read source action dominate; advanced filters, diagnostics and retrieval internals recede into native disclosures; result snippets retain source and relevance context. Saved questions remain beside the source rather than being portrayed as edits to it.
- **Consistency:** the opted-in navigation groups, surfaces, borders, accent treatment, active-location state and visible focus rules form one recognizable workspace. Native forms keep their explicit GET/POST routes and the progressive JavaScript does not replace academic data operations.

## Closure status

| Finding | Final disposition | Closure evidence |
| --- | --- | --- |
| U1 mobile Notes density | Closed; residual density tradeoff reflected in score | Refreshed 390/1366 library images show compact native source disclosure, paired course/type controls, visible ASCII plus, and first card around 730px. |
| U2 stale focus inertness | Closed | Repair computes inertness from current breakpoint/navigation state; implementation/engineering owner reports responsive closure checks. This reviewer rechecked visible, non-inert navigation after focus transitions through the hamburger at both 390 and 1366px. |
| U3 personal focus and tabs | Closed | Refreshed personal-reader screenshots show focus and tools controls; repaired tab/panel semantics were read. This reviewer ran the reversible focus tests for both readers plus the ordinary-motion drawer keyboard-focus case: **3 passed in 1.66s**. |
| U4 no-JS navigation | Closed | This reviewer's fresh JavaScript-disabled deep-reader journey opened the native disclosure, counted all 12 main destinations, and followed Resources to `/resources`. |
| U5 focus hamburger conflict | Closed | This reviewer's fresh Chromium checks at 390 and 1366px yielded sidebar `display:flex`, `inert:false`, focus `false`, and toggle expanded `true` after Focus → hamburger. |

Additional independent check: the final native Notes reader has `documentElement.scrollWidth=390` at a 390px viewport. One refreshed full-page Obsidian image omitted the offscreen table paint while leaving its frame visible. A live element screenshot after scrolling it into view showed every header and both rows correctly; the DOM reported visible content. This is a capture artifact, not missing product data, and was reported to the implementation owner for evidence recapture.

No product changes, commits, pushes, or production-data tests were performed by this UX reviewer. Final full-suite and protected-surface outcomes belong to the release evidence, not to the visual scoring table.
