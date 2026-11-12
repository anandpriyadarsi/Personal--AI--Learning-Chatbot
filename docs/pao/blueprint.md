# ANVAYA PAO — Implementation Blueprint for GPT-6 Work

**Finalized:** 12 November 2026. **Verified main:** abe8b3ee21689aede76eb8c325a7687e470812eb (rechecked on final delivery). **Spec:** ANVAYA_PAO_Astra6_Audit_Report.md.

**Goal:** A dependable daily planner, an evidence-based weekly review, and a safe connected Obsidian reader, joined through existing academic identities.

**Architecture:** Extend Flask/Jinja, services and repositories. Retain separate authoritative academic SQLite, Learning Studio, native Notes and original-file stores. Join through qualified IDs and versions; do not create a second planner or migrate every store into one database.

**Stack:** Existing Python, Flask, SQLite, Jinja, scoped CSS, small progressive JavaScript, Mistune and PyYAML. No new frontend framework, graph engine, queue, OAuth or AI provider required.

> This is a proposed execution plan, not an implementation claim. Follow packages in dependency order, with focused tests and review. The audit did not authorize code changes or merging. A future implementation request may authorize this blueprint; merging requires authorization in that session.

## 1. Scope and decisions

- Local web only; no Android APK, emulator, native runtime, public deployment or release-pipeline changes.
- Preserve academic records, source bytes, native Notes, Assessment grading, Library originals, Learning attempts and Tutor/Coding conversations.
- Keep owner-published WAL snapshots and source freshness checks. No startup/GET migrations, automatic task creation, source indexing or progress mutation.
- No mastery, independence or official grade inferred from reading, time, task completion, self-report or Colab output.
- Keep optional Tutor/Coding flags unchanged. Main already includes PR #72. Open #61/#68 are not evidence their features are absent.
- Safety foundation WP0–WP3 is independently deliverable. MVP is WP0–WP8. WP9 is explicitly optional.
- Recommended default: read-only external vault, explicit copy/export, user-entered availability, no reminders, no Google Calendar sync, no full graph or new rich editor.

### Alternatives resolved

| Choice | Alternative | Selected approach and reason |
|---|---|---|
| Extend SSR | New SPA/API replacement | SSR: existing native forms and browser tests work without JS; less mobile and regression cost. |
| Federated owner projections | Consolidate all stores | Federated: preserve source authority and existing migrations; shared references provide the needed joins. |
| Aggregate rows plus command/work receipts | Full event-sourced rewrite | Receipts: fixes replay/history problems without rebuilding every service. |
| Read-only vault plus explicit transfers | Managed writeback | Read-only MVP; managed writeback later requires expected-hash diff, backup and conflict recovery. Neither is automatic sync. |
| Explicit manifest refresh | Always-on filesystem watcher | Explicit first: predictable cross-platform ownership; later watcher may call the same refresh service. |
| Optional ICS export | Google OAuth/two-way sync | Export later, after task correctness; do not add credentials/conflicts to MVP. |

## 2. Exact change map

All abbreviated paths beginning P/ expand to personal_learning_assistant/. New files are proposals, not existing implementation claims.

| Area | Existing files to reuse/modify | Proposed new files |
|---|---|---|
| Commands | P/ui/web/routes.py; obsidian_connections.py; planning_proposals.py; planning_approval_controls.py; mobile.py | P/ui/web/pao_commands.py: shared scoped guards and errors |
| Task execution | P/services/operational_task_service.py, daily_agenda_service.py, month_plan_import_service.py; P/repositories/sqlite/planner_task_repository.py, daily_agenda_repository.py, month_plan_import_repository.py | P/services/planner_execution_service.py; P/repositories/sqlite/planner_execution_repository.py |
| Proposals | P/services/operational_planner_web_service.py; existing proposal/day routes | P/repositories/sqlite/planner_proposal_repository.py |
| Analysis | P/services/academic_overview_service.py, weekly_review_service.py; P/repositories/sqlite/weekly_review_repository.py; P/learning_studio/analysis_view.py | P/domain/weekly_evidence.py; P/services/weekly_evidence_service.py |
| Actions | P/domain/academic_evidence.py; P/services/academic_evidence_service.py; P/ui/web/academic_evidence.py; existing manual study intents | P/services/study_action_service.py |
| Vault identity | P/services/obsidian_workspace_service.py, obsidian_study_companion_service.py, study_item_resolver.py, obsidian_connection_service.py, obsidian_vault_registry_service.py; P/repositories/sqlite/obsidian_study_repository_v2.py, obsidian_vault_repository.py | P/services/obsidian_source_identity_service.py; P/repositories/sqlite/obsidian_source_identity_repository.py; extend existing registry rather than duplicate its graph |
| Safe reads and links | P/repositories/filesystem/obsidian_workspace_reader.py, obsidian_vault_scanner.py, knowledge_repository.py; root obsidian_integration.py; P/services/unified_search_service.py, obsidian_markdown_renderer.py | P/services/obsidian_manifest_service.py; P/services/obsidian_link_resolver.py |
| UI | P/ui/web/templates/planning.html, planning_tasks.html, planning_day.html, planning_weekly_review.html, analysis.html, learning_analysis_component.html, obsidian.html, obsidian_note.html, obsidian_connection.html; P/ui/web/static/planning_analysis.css; static/js/obsidian_reader.js | Small template partials _planning_capture.html, _weekly_actions.html, _source_reference.html |
| Activation | Existing migration_runner.py/activation/backup conventions | scripts/pao_migrate.py; docs/pao/ runbook; next unused optional migrations |

Leave original academic content, Assessment answer keys/scoring, Tutor/Coding execution/consent, native Notes bodies, Learning package revisions and PDF/PPT originals untouched. Do not revive retired legacy Notes Studio write routes merely because their backend exists.

## 3. Normative data contracts

### 3.1 Qualified references

Reuse canonical_topic_reference and SourceReference from P/domain/academic_evidence.py. Add a compatible adapter for owner, kind, stable identifier, optional revision/hash, safe logical locator, course_id/topic_id, and mapping_status (confirmed/unreviewed/missing/conflict). Owner is one of academic, learning, native_note, obsidian, library, tutor. Never resolve by fuzzy course name.

Proposed planner_task_sources relation: task_id, owner, kind, identifier, revision_key, sha256, mapping_status; unique on task/owner/kind/identifier/revision_key. A deleted source leaves a labeled historical reference. URLs are generated by a server allowlist; clients cannot supply arbitrary destinations. Tokens contain identities/fingerprints, not source text, answer keys or absolute host paths.

### 3.2 Canonical task commands and work logs

Keep planner_tasks.id and current fields. Add revision incremented by every mutation; keep manual_revision's legacy import-protection meaning. Proposed interfaces:

~~~text
transition_task(task_id, expected_revision, command_id, target_status,
                agenda_item_id=None, actual_minutes=None, note='') -> CommandReceipt
log_progress(task_id, expected_revision, command_id, occurred_at,
             actual_minutes, agenda_item_id=None, note='') -> CommandReceipt
~~~

Within one BEGIN IMMEDIATE transaction: check existing command identity first. Matching payload returns the stored receipt even if the current revision has since advanced; different payload conflicts. Only unseen commands validate current revision/state, record receipt/work log, update canonical task and agenda projection, then commit. Same command UUID and payload returns original result; same UUID/different payload or stale revision returns 409. Check affected row counts. An archived canonical task cannot leave a newly completed agenda receipt.

Proposed planner_command_receipts stores command ID, payload hash, task ID, prior/new revision, action, occurrence instant and result. planner_work_logs stores log ID, task/agenda reference, actual minutes, occurrence instant, self_reported evidence label, optional supersedes ID. Multiple partial logs are valid; terminal completion is singular unless an explicit later reopen lifecycle is designed. Corrections append a superseding record.

Avoid double-counting work logs and derived daily_agenda_items.actual_minutes. Use unique origin_agenda_item_id for a legacy bridge. Preserve study_plan_item completion and its existing study_session receipt owner; combine through deduplicating adapters, not a second receipt for the same work.

Imports own proposed title/schedule metadata, not execution status/actual history. Refresh cannot reopen completed/archived tasks. Show field-level conflicts in preview. Exact hash reimport remains no-op; validate raw collection cardinality before slicing/normalization.

### 3.3 Durable proposal

Proposed record: id, agenda_id/date, revision, timezone, availability_windows_json, policy_version, candidate_refs_json, source_versions_json, preview_hash, status, created_at/approved_at. Windows contain local date/start/end plus derived UTC instants. Reject overlapping/invalid/ambiguous windows. Existing one-window form maps to a one-element list.

Signed approval binds ID/revision/purpose/nonce/expiry. Business context is durable; signing keys may still rotate on restart. Reopen saved draft, revalidate and issue fresh token without requiring re-entry or duplicate save. Approval atomically checks relevant commitments/candidates, not every lifetime planner row. Changed relevant source produces diff/re-preview; unrelated review should not invalidate it.

### 3.4 Obsidian identity

Proposed additive model: connections(id UUID, mode, display_name, root_locator, enabled, active_manifest_revision); source_items(id UUID, connection_id, external_uuid, relative_path, sha256, state, revision); source_aliases(connection_id, old_path, item_id, confirmed_at, provenance); source_versions(item_id, hash, metadata, observed_at).

One active connection is enough for MVP. Refresh ZIP updates a selected connection version; explicit Replace connection creates a new connection. Root relocation changes locator only. Canonical study identity becomes obsidian-source:<item UUID>. External assistant_id is only a validated hint within a connection. Duplicate IDs block annotations while allowing safe read-only content. Same UUID in another connection is distinct. Identical text/hash never implies identical note.

Reuse existing registry and rename-aware behavior. Path continuity supports refresh; ambiguous rename/copy candidates require explicit reconciliation. Do not insert UUID frontmatter into original Markdown. Current bare-UUID history may already be ambiguous: retain it in an unresolved legacy view, never assign to whichever vault is connected today.

### 3.5 Evidence envelope

Metric(value, unit, status, scope, as_of, numerator, denominator, source_refs, policy_version, exclusions). Status is available/partial/empty/unavailable. Scope includes dates, timezone, exact course ID and source-specific filter. Source refs support paging without exposing answers. Independent owners have independent freshness, not a claimed atomic global snapshot.

Closed weekly review stores metrics JSON, evidence IDs/fingerprints, as_of and policy version. Retain existing integer columns for compatibility. Old snapshots lacking provenance/coverage show Legacy snapshot; coverage unavailable. Do not invent missing history from current rows.

## 4. Metric specification

Live projections recalculate on read after the listed owner changes; caches key by source revision/scope. Closing review freezes a snapshot. No timer mutation is required.

| Metric | Inputs/calculation | Update trigger and interpretation | No-data fallback |
|---|---|---|---|
| Approved scheduled minutes | Task/study/manual items with verified approval evidence (approved_at or approval receipt) and valid allocated start/end; sum planned_minutes; exclude fixed classes/routines. Closed status alone does not prove approval | Approval/reschedule/close; allocated intention, not learning | 0 when healthy and none; unknown when unavailable; show unallocated estimates separately |
| Actual minutes | Explicit work logs plus legacy values without corresponding log, deduped by origin | Log/correction; self-reported effort, not browser reading time | Null when all missing; 0 only explicitly known; display coverage |
| Logging coverage | Eligible execution items with known actual / all eligible items | Execution/log changes; completeness of recording | 0/0 means No eligible sessions, not 0% productivity |
| Distinct completed tasks | Distinct canonical task IDs with valid terminal receipt in period | Completion/correction; task outcomes | Zero if healthy; undated historical completion unknown/excluded |
| Planned-work completion | Completed eligible approved occurrences / all eligible approved occurrences; exclude moved/canceled before start with reason | Approval/execution/reschedule | No percentage for zero denominator; separate from distinct tasks |
| Deadline outcomes | Due tasks in period; date-only end of local day; compare first completion instant to deadline and review as_of | Due-date/completion change; on-time/late/unresolved/upcoming/unknown | Independent of agenda existence; missing deadline unknown; never independent SQL date('now') |
| Assessment outcomes | Qualified session marks and own denominator/evaluator/date | Submission/grading; no average across unlike tests | Filter before paging; honest total/sample scope; unknown is not failed |
| Topic recheck | Latest qualified outcome per exact question ID/revision, separate assessment/practice counts and dates | New attempt/evaluation; candidate for review, not mastery | Unmapped/sparse => insufficient evidence; no confidence score |
| Upcoming workload | Open tasks due next 7 local days; known estimate sum plus count lacking estimates | Task/estimate/window edits; rough demand | No availability => no overload ratio; no estimates => Effort not entered |
| Revision queue | Explicit review tasks and next_review_on/source refs | User schedules/completes/replans | Empty queue; no invented forgetting curve |
| Weekly comparison | Same definition/policy/scope across adjacent weeks, with coverage | Evidence update/close | Hide delta if incompatible/insufficient coverage; explain why |

Exam view shows known dates, linked topics/tasks and evidence age. No readiness percentage. Notes inventory is all-time collection information, not learning performance. Do not add streaks to the main decision view.

## 5. Migration and recovery

1. Dry-run actual stores/schema/flags/WAL state, vault registry/config and note assets. Report contradictory task status/timestamps, duplicate IDs, dangling references and ambiguous histories without dumping private content.
2. Stop writers or use established consistent SQLite online backup. Never copy only DB while live WAL holds committed data. Back up config and metadata/assets separately; hash originals. Verify restored backup integrity before applying anything.
3. Use next unused optional migrations; 0015/0016/0017 already exist. Add tables/columns and mapping ledger transactionally; retain old tables/content. No GET/startup migration. Rehearse on restored disposable copy.
4. Backfill only provable one-to-one facts. Existing timestamps can become legacy-labeled completion evidence, not fabricated minutes. Conflicting completed/archived rows and duplicate completion history remain flagged for review. Closed agendas lacking approval evidence remain unapproved/unknown; never fabricate approved_at.
5. Use old vault-scoped rows/registry for identity reconciliation. Bare shared UUID histories remain unresolved; missing sources retain reference/tombstone. ZIP refresh never deletes copies/history.
6. Second apply is no-op; interruption rolls back safely; dry-run leaves DB/sidecars/index unchanged. Record version/checksum and old/new identity evidence.
7. Feature-off rollback preserves new tables and read-only history/export. Do not restore a backup over newer activity without exporting/reconciling it. Full restore requires deliberate choice, not an automatic failure handler.

Proposed flags ANVAYA_PAO_V3_ENABLED and ANVAYA_OBSIDIAN_IDENTITY_V3_ENABLED default false until readiness/migration succeeds. Security fixes remain active with flags off. Existing optional Tutor flags stay unchanged.

## 6. Work packages

Each package: write focused regression/acceptance test; verify baseline failure/missing behavior; implement minimum change; run relevant tests; perform listed browser journey; review and record exact commit. Do not run unrelated full matrices repeatedly for small UI changes, but widen checks for persistence/security changes.

### WP0 — Baseline (small)

**Files:** read current instructions, launcher/config, pinned requirements, optional migrations and audit test paths; add docs/pao/baseline.md in implementation branch.

- [ ] Compare current main to audited commit; inspect only relevant changed owners.
- [ ] Use isolated checkout and disposable fixtures; avoid normal launcher against personal data because it activates/initializes stores.
- [ ] Run three baseline test groups in section 7 with pinned dependencies; record environment/skips.

**Acceptance/browser:** record 390px/1366px empty, populated and unavailable states. **Boundary:** no personal source mutations. Unknown installation flags are blockers to activation, not reasons to guess.

### WP1 — Command/read safety and import cardinality (medium, P0)

**Files:** command/route/read map in section 2; month_plan_import_service.py. **Interfaces:** require_local_command(scope, token); read_verified_source(connection, relative_path, expected_hash=None, max_bytes=...). Reuse guarded reader.

- [ ] Add tests/test_pao_command_boundaries.py: old and new aliases reject cross-origin, missing/bad/expired token before service invocation; valid same-origin works; host validation.
- [ ] Test 999/1000/1001 import items, mixed categories, invalid collection shapes and >2 MB payload; reject overflow explicitly before slicing.
- [ ] Test file/directory/root symlinks, traversal, absolute path, changed file and byte bounds across reader AND knowledge ingestion.
- [ ] Retire unused legacy write aliases or route through same guard; preserve signed approval semantics.

**Acceptance:** rejected requests call no writer; unsafe sources never read; no partial import/config changes. **Browser:** invalid token/file, refresh/retry, valid connection. **Regression:** Tutor/Assessment boundaries unchanged; no outside-root reads or new LAN exposure.

### WP2 — Canonical execution and reconciliation (large, P0/P1)

**Files:** task/day/import services/repositories; new execution owner and optional migration; task/day templates. **Interfaces:** section 3.2.

- [ ] Add tests/test_pao_task_integrity.py for complete→changed import, two preapproved agendas, archive-between-submit, stale revision and duplicate command payload.
- [ ] Implement transactionally checked state/revision/receipt and agenda projection; check row counts and timestamps.
- [ ] Import preview separates source-owned metadata from execution state; changed source cannot reopen terminal work.
- [ ] Add explicit partial work log and optional remaining estimate; final completion separate; corrections append history.

**Acceptance:** one command/terminal completion; multiple legitimate partial logs counted once; import preserves completion. **Browser:** create→plan→partial→reload→complete; old tab and changed import. **Regression:** study_plan_item receipts, manual-study intent dedupe, Assessment recovery tasks.

### WP3 — Stable Obsidian identity and repair (large, P0)

**Files:** identity/registry/companion/resolver/connection map and optional migration. **Interfaces:** resolve_source(connection_id,path), resolve_study_identity(item_id), preview_identity_migration(), apply_identity_migration(expected_report_hash).

- [ ] Add tests/test_pao_obsidian_identity.py: cross-vault same UUID, same-vault duplicate, identical copies, confirmed rename, root relocation and snapshot refresh.
- [ ] Implement stable IDs and conservative mapping ledger; ambiguous history remains accessible as unresolved, not silently moved.
- [ ] Update all reader/search/companion identity consumers consistently; no original frontmatter edits.

**Acceptance:** isolated annotations; replay migration no-op; interrupted apply preserves records. **Browser:** duplicate conflict, safe reading, refresh snapshot/history. **Regression:** legacy 0005/current 0007 compatibility, backup restore, independent native Notes.

### WP4 — Weekly evidence and concise Analysis (medium, P1)

**Files:** weekly domain/service, overview/review repositories/services and templates. **Interface:** review(start,end,course_id,as_of) returns metrics/scope/provenance; close_review(expected_revision,evidence_fingerprint,reflection) freezes displayed snapshot.

- [ ] Add tests/test_pao_weekly_metrics.py: overdue with no agenda, draft/unallocated exclusion including scheduled draft closed without approval, null/zero, deduped logs, historical deadlines, closed snapshot stable after later edits.
- [ ] Test >100 mixed sessions and priority-skewed tasks; filter population before pagination or explicitly label sampling; separate aggregate counts.
- [ ] Implement metric contract in both views; separate source scopes and unavailable/empty states.
- [ ] Put weekly facts/actions first; Notes donut/legacy inventory secondary; retain full-history access.

**Acceptance:** same definition yields same values; closed review immutable; no mastery inference. **Browser:** filters/provenance, sparse/unavailable, 200% zoom. **Regression:** WAL age/inventory safety, answer-key secrecy, Notes and Learning source scope.

### WP5 — Capture and student navigation (medium, P1)

**Files:** task routes/service, catalogue adapter, Planning templates/CSS. **Interface:** optional exact course/topic/assessment references validated by active catalogue; unlinked tasks remain allowed.

- [ ] Add tests/test_pao_capture.py: course-filter visibility, cross-course topic rejection, completed/archived labels and legal transitions, preserved form on error.
- [ ] Build Today/This Week/Backlog/Exams using existing owners and URLs; month import secondary.
- [ ] Title-first capture with expandable details; validated date/weekday/none preference, old invalid text visibly Needs timing review.
- [ ] Task-specific deep links and retained filters; Exams only real/unknown assessment dates.

**Acceptance:** capture-to-course possible in UI; All tasks retains unlinked work; no illegal Complete on skipped task. **Browser:** phone keyboard, long title, errors, history/back navigation. **Regression:** IDs/imports/calendar/assessment data.

### WP6 — Durable capacity and useful scheduling (medium-large, P1)

**Files:** proposal store, scheduler, web service, approval/day templates. **Interfaces:** pure preview_proposal(date,windows,policy,context); save_proposal(hash,command_id); approve_proposal(id,revision,command_id).

- [ ] Add tests/test_pao_proposal_durability.py: save/restart/reopen, fresh approval token, relevant source conflict, unrelated activity unchanged, duplicate save/approve.
- [ ] Test five overdue blockers plus feasible sixth, small fitting candidate behind large one, unknown fixed occupancy, overlapping windows and elapsed slots.
- [ ] Select feasible placements before final cap; preserve visible review-needed queue and reason codes. Never silently revise overdue deadlines.
- [ ] Persist windows/context, expose break/cap policy, support multiple user-entered windows and deliberate reschedule history.

**Acceptance:** no invented capacity; restart retains inputs; useful eligible candidates visible. **Browser:** classes plus morning/evening windows, missed block, restart and stale approval. **Regression:** timezone validation, source snapshots, explicit approval and existing deep-work policies.

### WP7 — Evidence-to-task and source-to-study (medium, P1)

**Files:** academic evidence/manual intents, source relation and study-action service/templates. **Interfaces:** suggest_actions(context,max_actions=3); preview_action(candidate,current_sources); accept_action(intent_id,fingerprint).

- [ ] Add tests/test_pao_study_actions.py: exact source/topic carried, stale/deleted source blocked, double-click one task, no grade/provider/mastery side effects.
- [ ] Deterministic reviewed suggestions: user overdue commitments, qualified recheck, explicit due revision; max three; explain evidence/date/qualification.
- [ ] Preview editable title/estimate/date before create; reuse existing manual study intent receipt. Never fuzzy-map or silently create urgency.
- [ ] Open exact lesson/question/source or existing Coding task; hash/revision revalidation; Tutor owns provider consent. Feature-off paths give honest alternatives.

**Acceptance/browser:** complete plan→study→assessment→review→new task loop; unavailable source and duplicate submit safe. **Regression:** grading secrecy, Tutor consent/history, Learning dedupe and original bytes.

### WP8 — Bounded reader, faithful links and transfers (medium-large, P1)

**Files:** manifest/resolver, filesystem reader/scanner, workspace/companion/search/renderer/connection, source-copy metadata. **Interfaces:** explicit refresh_manifest(connection,revision); bounded validate_note_version(item,hash); resolve_link(item,target); preview_copy(refs) with expected versions.

- [ ] Add tests/test_pao_vault_read_cost.py: heartbeat opens selected note only; search avoids per-result whole-vault rescan; bounded folder size/count, changed/missing source status.
- [ ] Test fenced/inline code unchanged; no frontmatter/code backlinks; relative/wiki/Markdown links, exact paths, ambiguous basenames, Unicode, heading/block anchors and XSS.
- [ ] Share derived manifest/graph. GET does not silently persist refresh; changed source shows stale/retry; cache keyed by source and connection revision.
- [ ] Wire safe local raster route into renderer, restrict remote images by explicit policy. Markdown-only ZIP remains acceptable if omitted assets are listed and missing assets explained; asset ZIP support optional with MIME/path/byte budgets.
- [ ] Copy records immutable copied_from provenance; repeat import offers skip or independent copy, never overwrite edited Notes. Explicit Markdown download/export preserves raw text/unknown frontmatter and includes exclusions. Snapshot cleanup requires explicit selection, never disconnect deletion.

**Acceptance:** source bytes intact, no cross-root assets, code fidelity, deliberate duplicates, honest index freshness. **Browser:** search/backlinks, focus drawer, conflict, copy/reload/export at 320/390/1366px. **Regression:** hostile ZIP, atomic Notes batch, companion/registry suites.

**Performance:** instrument read counts and p50/p95 on synthetic 100/1,000/10,000-note vaults. Structural gate: heartbeat cost independent of vault size, search no result-count multiplication of full scan. Record hardware/limits; no desktop benchmark claimed as physical M11 performance. Paginate; no graph framework.

### WP9 — Optional enhancements

Exam templates with preview/dedupe and real dates; recurring task occurrences distinct from routine templates; selected approved ICS export with stable UID/timezone; managed writeback only with diff/hash/backup/conflict policy; reminders only after channel and always-running delivery mechanism chosen. No generic readiness score or automatic two-way sync.

## 7. Verification and completion gates

Baseline from repository root, pinned dependencies:

~~~bash
python -m pytest -q tests/test_planning_analysis_v2.py tests/test_planning_v2_review_regressions.py tests/test_planning_v21_wal_snapshot.py
python -m pytest -q tests/test_obsidian_connections.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase5_obsidian_vault_registry.py
python -m pytest -q tests/test_planning_analysis_v2_browser.py
~~~

Use repository verification dependency policy to add affected task/day/month/week, evidence, Learning/Tutor handoff, Notes separation and migration/backup checks. Run new package tests too. Persistence/security changes need wider checks than CSS; do not rerun unrelated matrices after every minor edit or use skip markers to disguise required gaps.

- [ ] Every P0 reproduction corrected with committed regression.
- [ ] Migration dry-run/apply/retry/interruption/rollback proven on disposable restored copy; ambiguous history not assigned arbitrarily.
- [ ] Before/after original hashes, marks, attempts, Notes assets and conversations preserved.
- [ ] Weekly metric definitions consistent; closed snapshots stable; unknown distinct from zero.
- [ ] All mutation aliases guarded; safe file boundary shared by reader/ingestion.
- [ ] Real browser desktop and 320/390px with JS on and native forms without JS: keyboard, zoom, empty/error, stale source, two tabs, restart and persistence.
- [ ] Relevant pinned Windows/Linux verification before cross-platform claims; physical phone separate; no Android gate required.
- [ ] Exact tested SHA, files, results/skips/limitations, activation/run/backup/rollback instructions and remaining work documented.
- [ ] Merge/publish only if separately authorized and gates passed.

Review focus: contradictory terminal timestamps (WP2), copied-vault UUIDs (WP3), source changes between preview/submit (WP7/8), missing WAL/vault (WP4/8), old-tab replay after restart (WP1/6).

## 8. Ready-to-paste execution brief

~~~text
Implement the local-web ANVAYA PAO MVP from the attached
ANVAYA_PAO_Implementation_Blueprint_for_Work.md and
ANVAYA_PAO_Astra6_Audit_Report.md.

Repository: anandpriyadarsi/Personal--AI--Learning-Chatbot.
Audit baseline: abe8b3ee21689aede76eb8c325a7687e470812eb.
Inspect current main and relevant differences. Do actual staged implementation,
not another generic audit. Execute WP0–WP8; WP9 is optional.

Start with regressions for changed import reopening completed work, duplicate
completion/stale archive races, truncated imports, unsafe legacy command/file
paths, duplicate/cross-vault Obsidian identities, and inconsistent weekly totals.

Preserve Flask/service/repository architecture and existing academic data,
Tutor/Coding, Assessment, Library, Learning Studio, Notes and original files.
Use canonical task commands, durable proposals, conservative additive identity
migrations, qualified evidence and existing explicit manual-study intents.
No inferred mastery/grades, student-code execution, vault writeback, cloud
calendar sync, Android work or public deployment.

Deliver compact Today/Week/Backlog/Exams, weekly evidence with at most three
reviewed suggested actions, and safe bounded Obsidian reading and transfers.
Test real desktop/mobile-width browsers and relevant Windows/Linux paths.
Preserve exact evidence; report unavailable checks honestly. Use synthetic data.

Provide tested SHA, changes, verification, run commands, backup/migration/rollback
guide and completed/remaining checklist. Prepare reviewable changes. Do not
merge or publish without authorization in this implementation session.
~~~
