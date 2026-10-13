# Gate A automation implementation plan

> Execute inline with `superpowers:executing-plans`; independently review the whole delta before commit. User's attached master prompt authorizes this scope and resolves design approval.

**Goal:** A reproducible Linux/Windows development baseline using disposable data, without certifying production authority.

**Architecture:** Scoped migrated test fixtures use existing service factories. A Python validator exports only tracked source into a fresh temporary checkout, runs the unchanged full suite plus focused/order/browser/Node/integrity checks, and records explicit category results. CI invokes the same validator on Ubuntu and Windows. Characterization remains separate from product acceptance.

**Tech stack:** Existing Flask, SQLite, pytest, Node and Playwright; scientific packages confined to test requirements.

**Spec:** Attached ANVAYA_NEXT_WORK_MASTER_PROMPT dated 11 October and architecture bundle (source f859a3c).

## Global constraints

- No production data, schema/migration changes, Tutor/Library merge, planner/Analysis behavior changes or main merge in A1.
- No test deselection, blanket skip, weakened assertions, real provider or root database seed.
- Development automation and local production authority are distinct gates.
- Assessment changes here are concrete technical designs; persistence implementation awaits verified migration lineage.

## Review focus

- Export must never include ignored personal files, symlinks or untracked credentials.
- Failed/missing/skipped browser execution cannot produce a green development gate.
- Fixture injection must be scoped and must exercise real service/repository reads.
- Windows subprocess paths, Node glob expansion, temporary file cleanup and timezone database availability must be portable.
- Self-assessment design must not leak secrets or promote self-reported marks into independent evidence.

## Tasks

1. Reproduce all 17 original failures in a fresh environment. Add explicit synthetic fixture tests for deterministic IDs, root absence, knowledge/session data, FK integrity and refused overwrite. Replace copied root DB helper and inject real scoped service in the two GET tests and shell smoke. Pin installed/tested Pandas and Matplotlib under requirements-dev. Run original failing files and Phase2 in both orders, retaining all existing safety assertions.
2. Add validator tests first: reject unsafe/nonempty/symlink output, source export isolation, failed/skipped result propagation and machine/human summary. Implement `scripts/architecture_validation.py --output PATH` using fresh owned temp source. Seed only an explicit fixture DB; run all pytest unchanged, original focused set, both order checks, Node via expanded file paths, fresh migrations twice/checksums/FKs, compile, pip check and browser tests. Capture logs/XML/screenshots, source SHA, versions and file/logical effects.
3. Port inspected A–D/P01–P08 scripts into characterization tests with exact current-defect assertions and owner/future-test metadata. Keep reproduction PASS distinct from desired behavior FAIL. Add responsive/keyboard/zoom/timer/interruption/reopen synthetic browser assertions and screenshots. Add GitHub Actions matrix and thin PowerShell wrapper. Run validator locally; after green independently reviewed source, commit/push A branch and observe actual Ubuntu/Windows jobs.
4. Read runner/package/evaluation/intelligence/SQL/UI contracts; write `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`, implementation addendum and redacted one-command local identity/schema-copy collector. Test collector refusal/redaction/readonly effects. Design full race/idempotency/reveal/self-grade contracts; no migration applied.
5. Only after actual development automation passes, implement separate no-migration B1 read-only adapter branch: explicit existing DB snapshot, course/topic validation, immutable DTOs, evaluation/bridge IDs, unknown historical mapping/independence, no automatic qualification and no consumer changes. Test actual SQL reads and file/sidecar effects, run full validator, independent review and commit/push only green work. Defer schema writer/UI/recovery slots explicitly.

## Ledger

- Baseline: f859a3c; remote unchanged; seven historical branches inspected read-only. Isolated feature worktree created. EOL-only backup/dashboard blobs retained via local Git attributes, no source normalization.
- Ruling: user's master prompt supersedes older audit stop/approval instructions; implement approved A1 and conditional source-only B1 without asking again. Cost if wrong: extra isolated feature work, never production writes.
- Tasks 1–4 implemented. Baseline 17 failures reproduced; original fixture assertions retained; scientific dependencies pinned; full isolated Linux run 1763 PASS with no skips, focused54/orders41each/browser39. Added collector race regression after that run, now14 harness/collector/fixture PASS.
- Independent whole-delta review found broad untracked export and single-platform/aggregate naming. Both repaired; reviewer confirms no remaining Critical/Important issues. Replay cwd/environment note repaired too. Final staged full validation and actual Ubuntu/Windows CI remain required.
- Export now uses tracked/staged files only; explicitly reviewed new files are staged before validation. Each platform CLI reports GATE_A_DEV_PLATFORM; aggregate CI certifies GATE_A_DEV_AUTOMATED only when both jobs pass.
- Task5 remains conditional, BLOCKED until actual cross-platform development evidence. Production migration authority independently remains BLOCKED.
- Resume 11 October: remote main remains f859a3c; feature HEAD70f6b153. Preserved and resumed the existing five-file uncommitted EOL/clean-source repair. Hosted run38114350936: Ubuntu PASS; Windows full1754 PASS/13 setup errors, all the same read_routes platform-separator assertion; headless39 PASS. No product assertion failed. Cross-platform gate remains FAIL until rerun.
- Windows characterization regression: actual child hash function with PureWindowsPath reproduces backslash inventory key vs portable slash assertion (RED); inventory now uses as_posix while preserving file hashes and original defect assertions (GREEN). Focused continuation suite29 PASS. Full validator and independent continuation review in progress.
- Ruling: retain the recovered EOL-only preparation with pristine-source checks because it verifies exact content equivalence before restoring only two historical blobs; no source normalization or blanket dirty-tree allowance. Cost if wrong: CI stops, and no B1 promotion occurs.
- Independent continuation reviewer: no findings; focused29 PASS. First resumed full run7qyq0imj:1733 passed/39 browser setup errors due to selecting incomplete cache path (executable absent), other categories PASS. Complete existing Chromium134.0.6998.35 installation located and launch verified; full rerun uses that path. CI still performs fresh Chromium installs. No skip/assertion changes.

Continuation final Linux run `run-7sojvroq`: full1772 PASS (0 failures/errors/skips), focused54, fixture orders41each, characterization17, browser39, Node20 and all15 categories PASS. Independent review clean. Implementation/workflow/test bytes match the validated source fingerprint `5536c816a7b02c16a5aba9679399677bab55b64f362a763405a726a5cbf2e3e4`; subsequent edits only record evidence. Hosted confirmation pending publication.
