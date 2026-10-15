# Learning Studio V1.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. User authorizes routine design/implementation and no repeated approval. Independent agents perform read-only content and final engineering review.

**Goal:** Complete trustworthy lesson-oriented learning, active revision/recovery, traceable coverage and self-sufficient validation from pushed V1.1.
**Architecture:** Preserve V1 imports/publications/attempts. Add V2 only for trusted relational graphs/widgets; keep coverage as a versioned companion and separate immutable feature-store record. Explicit feature-only migration adds append-only progress/engagement and coverage; selected-reader and Analysis consume read-only projections.
**Tech Stack:** Existing Python3.12, Flask, SQLite, escaped Mistune, Pillow/pypdf and local Chromium/Playwright; no reading CDN/provider dependency.
**Spec:** `docs/learning_studio/v1-2/master-instruction.md` (authoritative uploaded instruction).

## Global Constraints

- Base775941c730e8160501c849bc4971e8eb178331d1/tree0bb2f119fa67eadb99b1cd43d5481e012a0f93d0; only feature/learning-studio-v1-2 commits/push. No merge/force push.
- No production academic/Notes/Obsidian/Knowledge/Tutor/Assessment authority writes, source changes or other worktree modification.
- All GET/startup/Analysis/context/export pure; writes guarded by existing CSRF/origin/Fetch Metadata and bounded payloads.
- Immutable historical module/question/attempt integrity; source byte availability, inventory, fidelity, external facts and canonical mapping are distinct.
- Canonical real mapping stays null without live registry confirmation; all20 page statuses remain needs_review, not automatically verified.
- No imported HTML/SVG/JS/callbacks/URLs/eval. New graphs are validated data and internally generated escaped SVG plus matching text.
- Real source/package/screenshots stay private. Public CI executes realistic synthetic20-page gates; exactly existing4 external cases may skip without attachments.
- Final exact pushed-SHA Ubuntu/Windows scoped/delta gates; raw baseline failures stay RED and documented.

## Review Focus

- Old anchor links and older revision progress must target exact historical lesson/question without silent migration.
- Recovery after network interruption must neither duplicate graded events nor manufacture correctness from engagement.
- A source or notes change must invalidate companion review claims, including comparison relationship and list-member changes.
- Removed/renamed/unavailable catalogue metadata must not survive as current reviewed topic evidence.
- Malformed/oversized graph/widget/coverage data, foreign DBs and source paths must fail before writes.

### Task1: Versioned content contracts and source coverage

Files: validation.py, new content_blocks.py/coverage.py, archive.py; tests test_v12_contracts.py/test_coverage.py; schema/contracts.
Interfaces: V1 validate_package unchanged signature/default supported. V2 graph/activity kinds bounded/escaped. `decode_bundle(raw, filename)`→(package,assets,coverage or None), retaining legacy decode_upload pair. `validate_coverage(record,package,source,assets)`→deepcopy validated versioned companion. Inventory exact PDF text lines plus explicitly inspected visual elements; teaching targets and review source/content digests validated independently.
- [ ] RED tests V1 compatibility, graph/widget malformed IDs/edges/injection/limits, missing bullet/list member/relationship, unsupported visual, bad locator/source/stale content review.
- [ ] Implement contracts and canonical companions; no semantic auto-certification.
- [ ] GREEN contract/security tests; scoped commit and ledger.

### Task2: Feature-only migration, resume and mapping review

Files: store.py, new progress.py; service delegating methods; guarded Flask endpoints; tests test_v12_progress.py/test_migration.py/test_mapping_review.py.
Interfaces: store reads accept V1/V2 without migration; explicit writes migrate with validated feature-only backup/transaction. `record_progress(module_id,revision,payload)` / `reading_state(module_id,revision)` / nongraded engagement / companion stage/view. `stage(package,assets=None,coverage=None)` validates before writes. `mapping_candidates` reads exact live catalogue; confirmation creates next derived revision after live validation, preserving old attempts/questions.
- [ ] RED populated V1 migration preserves every row/source/key, foreign/symlink refusal, GET purity, idempotency, restart resume/old revision, forged completion/correctness and mapping tests.
- [ ] Implement additive schema2 tables/triggers and safe backup/rollback documentation; no downgrade losing state.
- [ ] GREEN store/service/write-boundary tests; scoped commit and ledger.

### Task3: Evidence, Analysis and honest Tutor boundary

Files: new evidence.py/tutor_bridge.py, service.py; learning_analysis.html/new integrated partial; app extension seam; tests test_v12_evidence.py/test_tutor_bridge.py.
Interfaces: evidence summary keeps compatibility fields but adds distinct question versions/current wrong/recovered/current mapping/historical mapping and per-group labels. Module-version signals expose bounded priorities and exact Review/Recheck/Revision links. Tutor boundary resolves only guarded module/revision/event action and bounded server producer; consumer enabled only if actual immutable source/owner/session seam exists. Otherwise503 honest incompatible boundary, zero provider/session writes, manual brief remains.
- [ ] RED initialized empty label,10 retries1 observation, removed/renamed/unavailable current mapping, group labels/actions and integrated GET purity.
- [ ] Inspect actual Tutor signatures and active branch; implement safe supported seam or documented BLOCKED consumer and all10 handoff tests +bounds/duplicates.
- [ ] GREEN evidence/Analysis/compatibility tests; scoped commit and ledger.

### Task4: Selected lesson/source/practice and active revision

Files: new reader.py, routes delegation, learning_module.html and focused partials, CSS/JS; pilot.py/new pilot_quality.py; tests test_v12_reader.py and upgraded actual browser/recovered cases.
Interfaces: server reader selection validates section/page/question/mode/budget; one lesson/page/question default, explicit all/full preserving old anchors. Query context links plus JS legacy-anchor translation. Explicit progress POST uses task2 durable state; no GET writes. V1 ordered diagrams honest; V2 graph/widget renderer trusted local. Pilot normalization keeps existing convert_pilot defaultV1/revision1; new normalization produces immutable revision2/V2 with exact original31 question dictionaries,12 cards and source-faithful additions/ledger. Old published revision remains available.
- [ ] RED selected/default/all/print/source request bounds and malformed selectors; durable resume and pending-review return; cards/activities/5/15/full revision, source uncertainty, network/duplicate grading.
- [ ] Implement calm teaching-first layout, optional verbatim comparison, outline/prev/next/context, comfortable adjustable text, bounded source zoom, single question/modes/pause/recheck and user-reported recall/activity.
- [ ] Run Chromium1920/1536/1366/1024/768/390/360; existing shell theme support only; keyboard, reduced motion, no-JS/storage denial; screenshot visual inspection/repairs.
- [ ] Execute actual20-page/31-question/12-card pilot in existing external cases, not extra skip-only gates. Independent all-page content review and targeted unresolved queue.
- [ ] GREEN all feature/browser and real-source gates; scoped commit and ledger.

### Task5: Authoring/preflight/healthcheck and CI

Files: new authoring.py; scripts/learning_studio_preflight.py/learning_studio_validate.py; synthetic canonical example/authoring guide/prompt; workflow and tests test_v12_tools.py.
Interfaces: strict preflight reports field/action errors before storage and never repairs hash; pilot normalization exports canonical private ZIP+companion. Validation CLI discovers root, checks pinned deps/interpreter/browser, forces built-in browser execution, temporary owned roots, unique per-run JSON/JUnit/logs, scopes health/feature/focused/all. CI base explicitly775941c forV1.2, unchanged other branch baselines.
- [ ] RED bad refs/key projection/hash/catalogue/resource bounds and missing dependency/browser diagnoses, no hidden skip, output ownership/retention.
- [ ] Implement commands/examples and run equivalent Ubuntu/PowerShell CI with private inputs absent/public synthetic material.
- [ ] Run full baseline vs exact feature sequentially with same pinned environment, all raw logs and exact failure/missing/skip sets retained.
- [ ] GREEN scoped/focused/static gates; scoped commit and ledger.

### Task6: Whole-branch reviews, private improved package and final evidence

Files: required V1.2 reports/coverage/quickstart/Tutor disposition and durable resume checkpoint; private package/evidence outside public repo.
- [ ] Obtain fresh independent full-diff engineering review and distinct actual content/learning-flow review; fix important findings RED→GREEN.
- [ ] Reconcile exact counts/source hashes/protected snapshots, private improved module revision2 and20-page companion ledger.
- [ ] Commit/push reviewed branch using exact tested-tree equality/CAS if shell push unavailable; no merge.
- [ ] Wait final pushed SHA Ubuntu+Windows conclusions; collect per-OS raw counts/artifacts and acceptance limits.
- [ ] Deliver persistent private evidence and improved pilot package; two-command demo, no mandatory Windows QA.
