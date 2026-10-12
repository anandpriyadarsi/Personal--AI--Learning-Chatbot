# ANVAYA Learning Studio V1 implementation report

Status: safe additive V1 reader/import/evidence slices implemented, tested, reviewed, committed and pushed. Full feature acceptance remains BLOCKED for the supplied pilot import and the production-dependent Tutor suite; Ubuntu/Windows CI is evaluated separately below. No merge to main.

## Repository and reuse

Verified base: main `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`. Dedicated branch: `feature/learning-studio-v1`.

Pushed implementation commits: `6181ee4a9b06a73145728ac91aa8ddbb57fc5ab0` (safe artifact/import/evidence domain), `ef4ba38ee42c2ceb86bb9ba310088ac40bc44249` (Flask reader/navigation/focus). Pushed cross-platform correction: `132444dd6e62f5845c871f57f3d3ed17a967bc48` (raw ZIP path preservation and NumPy fixture dependency). Pushed contract/CI/handoff commit: `9777cd02892058e4e1be859c8620e0b2c688e64a`. Later report-only commits may advance HEAD; run git rev-parse HEAD for the exact checked-out head. Remote tree hashes were compared to the locally tested trees and matched exactly. Shell Git had no credential; the installed GitHub connection uploaded those identical trees and advanced only the new feature branch without force.

Reused base.html, existing global sidebar app.js/app.css, original ANVAYA brand mark/wordmark, Flask lazy application/blueprint patterns, course catalogue read model, registered Knowledge source identity/logical-root resolver. Original extractor, Notes authority, Obsidian authority, academic migrations, Tutor reasoning/orchestration and official assessment stores were unchanged.

Scratch expiry invalidated the initial linked-worktree metadata. The task continued in an independent checkout rebuilt from the SAME verified base, preserving code/test content. No ongoing Tutor or planning checkout was switched/reset.

## Working slices

- /learning: compact registered-course cards and explicit unmapped group; year/semester labels use available catalogue data without fabrication.
- /learning/courses/<course_id>: units/topic labels, search/topic filter and bounded metadata pagination. Tests verify six registered synthetic courses ×12 modules.
- /learning/modules/<id>/<revision>: Overview, Learn, Visualise, Practice, Day-before-exam Revision, My Weak Questions and Original Source. Historical published revisions remain accessible.
- /learning/import and /learning/staged/<id>/<revision>: canonical structured JSON/ZIP validation, immutable staging and explicit source/mapping-rechecked publication.
- Server-authoritative append-only attempts, idempotency and old-version grading; wrong answers remain after a correct retry/reopen. No browser-authoritative learning store.
- /learning/analysis, /learning/evidence and /learning/evidence/export: read-only grouped/daily low-stakes summaries and history export. /analysis adds a link without altering existing analysis authority.
- Narrow documented LearningEvidenceSummary contract; Tutor review action is explicitly disabled because the existing /agent entry point cannot consume the source-versioned contract.

## Executed validation

Pinned Python dependencies and actual local Chromium headless shell were used. Commands below were executed from the feature checkout with a dedicated validation interpreter. Equivalent ordinary commands are documented in the Windows handoff.

| Gate | Actual result |
|---|---|
| ANVAYA_BROWSER_TESTS=1 ANVAYA_TEST_PILOT_ZIP=<attached archive> python -m pytest -q tests/learning_studio | 55 passed, 0 skipped, 0 failures |
| Browser subset, desktop1440/mobile390 | 3 passed; actual width expansion, focus/topbar/rail restoration, Contents/Escape, keyboard, storage failure, fullscreen denial, real logo, source links, print and retry history |
| Notes/Obsidian/focus/startup plus Assessment phases A–D focused regressions | 101 passed |
| Whole suite on unchanged base | 1,716 passed, 16 failed, 0 errors, 0 skips |
| Whole suite on feature | 1,771 passed, the same16 failed, 0 errors, 0 skips |
| Regression delta | Zero newly failing tests. Raw whole suite remains RED; baseline failures are not hidden/changed |
| Demo | 73 published synthetic modules: six×12 plus unmapped20-page reader; DB integrity ok, 0 FK violations |
| Static | compileall and git diff --check passed |
| Review | Independent review; all important findings repaired with RED→GREEN tests |

The sixteen raw failures require an absent production learning_assistant.db for legacy Phase7.5.9 Tutor fixtures or expect /agent200 when its backend is unavailable. The master prompt forbids using/modifying production academic data for routine feature validation. No attempt was made to manufacture that fixture or change Tutor tests. Full logs, summary, isolated JUnit and screenshots live under docs/learning_studio/validation.

The cross-platform ZIP gate now checks orig_filename before Windows normalisation; a hostile raw-filename regression reproduces that boundary on Linux. The optional actual-pilot test passed by verifying the expected integrity rejection. This is NOT a passing pilot import. A separate consistent synthetic20-page package demonstrates all source bytes/page previews and the reader/import path.

## Supplied pilot integrity blocker

The archive was inspected (proposed JSON, prototype HTML, original20-page PDF, full/revision notes and fidelity/UI reports). It contains31 authored MCQs,20 lessons and20 raster previews. However:

- JSON/report recorded PDF SHA-256: `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411`
- Actual enclosed PDF SHA-256: `f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b`

The strict pilot converter blocks before storage. No pilot course mapping, import or publication occurred. Obtain/verify the matching original or explicitly review a corrected manifest and every question source reference. No silent hash replacement and no claimed semantic certification.

## Acceptance matrix

| Requirement | Status |
|---|---|
| Real logo desktop/mobile/focus | VERIFIED |
| Actual wider collapse, Focus Reading, mobile/keyboard | VERIFIED |
| Six×12 course/unit/topic/module organisation | VERIFIED with isolated synthetic catalogue |
| All20 actual pilot pages inside deployed module | BLOCKED by inconsistent source hash; synthetic20-page capability verified |
| All seven views in Flask | VERIFIED with synthetic packages |
| Safe staged/versioned import and historical preservation | VERIFIED |
| Wrong→correct history, authoritative grade and idempotency | VERIFIED |
| Grounded Analysis / bounded Tutor integration | Analysis VERIFIED; Tutor contract documented and gated |
| Automated fixture/headless gates / Ubuntu+Windows CI | Local gates VERIFIED; see CI status below |
| Committed/pushed feature / no main merge | VERIFIED for implementation commits; report-only commits advance the same branch |

## Safety and limitations

Both uploaded attachments were hashed before/after and remain unchanged. All feature tests and demo writes use disposable SQLite/source fixtures. Diff review confirms no production academic/Tutor files, source originals, Notes/Obsidian assets, retrieval indexes or official assessment state are changed. Production Windows state was not available/read or used.

The broad scratch-worktree hash comparison became inconclusive after workspace expiry:843 originally recorded files disappeared and3 surviving unrelated test/dependency files changed outside this feature delta. The task did not write those paths; no claim is made that all concurrent workspace files remained unchanged. Attached-file hashes and the exact isolated feature diff are verified.

Deferred: automatic Moodle/PPT/PDF generation, richer equation/graph rendering, semantic verification, personal-note save adapter, offline evidence import and an actual Tutor evidence consumer. Derived content never auto-saves into Notes or Obsidian.

Minor follow-ups from review: removed-course module cards need a discovery bucket (historical URLs work); Focus Reading is transient across Contents/view navigation; related-lesson action opens Learn at the top (exact source-page links work). Optional-preview malformed-type finding was fixed, not deferred.

## Five-to-ten minute use

Follow ANVAYA_LEARNING_STUDIO_WINDOWS_HANDOFF.md: clone only feature/learning-studio-v1 into a separate folder, install requirements-learning-studio.txt in a fresh venv, start the explicit disposable demo at127.0.0.1:5091, open /learning. No main/Tutor worktree switch is required. Production-authored imports require existing Knowledge source registry and configured logical roots; use the separate dedicated feature DB only.

## Changed source paths

- `.github/workflows/learning-studio.yml`
- `.gitignore`
- `ANVAYA_LEARNING_STUDIO_EVIDENCE_CONTRACT.md`
- `ANVAYA_LEARNING_STUDIO_FUTURE_AUTOMATION.md`
- `ANVAYA_LEARNING_STUDIO_IMPORT_SCHEMA.md`
- `ANVAYA_LEARNING_STUDIO_WINDOWS_HANDOFF.md`
- `docs/learning_studio/learning-module-v1.schema.json`
- `docs/learning_studio/review.md`
- `docs/superpowers/plans/2026-10-11-learning-studio.md`
- `docs/superpowers/plans/learning-studio-master-instruction.md`
- `personal_learning_assistant/learning_studio/__init__.py`
- `personal_learning_assistant/learning_studio/archive.py`
- `personal_learning_assistant/learning_studio/demo.py`
- `personal_learning_assistant/learning_studio/pilot.py`
- `personal_learning_assistant/learning_studio/rendering.py`
- `personal_learning_assistant/learning_studio/service.py`
- `personal_learning_assistant/learning_studio/sources.py`
- `personal_learning_assistant/learning_studio/store.py`
- `personal_learning_assistant/learning_studio/validation.py`
- `personal_learning_assistant/ui/web/__init__.py`
- `personal_learning_assistant/ui/web/learning_studio.py`
- `personal_learning_assistant/ui/web/static/css/learning_studio.css`
- `personal_learning_assistant/ui/web/static/js/learning_studio.js`
- `personal_learning_assistant/ui/web/templates/analysis.html`
- `personal_learning_assistant/ui/web/templates/base.html`
- `personal_learning_assistant/ui/web/templates/learning_analysis.html`
- `personal_learning_assistant/ui/web/templates/learning_error.html`
- `personal_learning_assistant/ui/web/templates/learning_import.html`
- `personal_learning_assistant/ui/web/templates/learning_library.html`
- `personal_learning_assistant/ui/web/templates/learning_module.html`
- `requirements-learning-studio.txt`
- `scripts/learning_studio_regression_gate.py`
- `tests/learning_studio/__init__.py`
- `tests/learning_studio/helpers.py`
- `tests/learning_studio/test_boundaries.py`
- `tests/learning_studio/test_browser.py`
- `tests/learning_studio/test_pilot.py`
- `tests/learning_studio/test_routes.py`
- `tests/learning_studio/test_service.py`

## CI evidence

Initial run: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38201815139. Ubuntu isolated gate53 passed/1 skipped and startup/authority gate60 passed; full-suite collection stopped because NumPy was missing. Windows ran the browser gates but failed the unsafe-backslash fixture after ZipInfo platform normalisation (52 passed,1 failed,1 skipped). Neither failure was skipped or accepted. Both were repaired and a new Linux regression reproduces Windows normalisation before checking the raw archive name.

Replacement run: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38233007085 on code132444dd6e62f5845c871f57f3d3ed17a967bc48. Status is pending at report preparation; do not infer Windows or Ubuntu CI success from local results. This run executes55 isolated cases (the absent attached-pilot check may skip in CI), startup separation and the full baseline/feature comparison. No production fixture is fabricated.
