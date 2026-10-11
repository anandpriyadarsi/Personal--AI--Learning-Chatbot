# ANVAYA Gate A automated validation report — 11 October 2026

Gate A1 implements test portability and development automation on `anvaya/gate-a-automated-validation`. No application behavior, SQL migration, academic records, Analysis, planner or old Tutor/Library implementation is changed. Main remains `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`; Coding Helper 2 is retained. The user's master prompt is execution authority. Older audit reports remain dated evidence.

## Gate distinction

| Gate | Status | Evidence/boundary |
|---|---|---|
| GATE_A_DEV_PLATFORM — local Linux | PASS | Clean disposable snapshot run `run-62m06053`: full 1763, focused 54, both orders 41 each, characterization 13, browser 39; all exit 0, no failures/errors/skips. Final reviewed rerun recorded below. |
| GATE_A_DEV_AUTOMATED — Ubuntu + Windows | BLOCKED | Workflow is implemented; matching actual jobs and aggregate acceptance still required. Single-OS CLI results cannot unlock B1. |
| GATE_A_LOCAL_PRODUCTION_AUTHORITY | BLOCKED | Installed Windows launcher/interpreter/backend, closed stable schema/ledger and normalized/projection parity have not been observed. Synthetic migration checks are not production lineage. |
| ASSESSMENT_PAUSE_RESUME_DESIGN | PASS | Concrete execution policy, timer, state machine, transactional races, API/UI, compatibility, tests and rollout in Assessment spec. Product implementation NOT RUN. |
| ASSESSMENT_PAPER_SUBJECTIVE_DESIGN | PASS | Structured/free-text rubric handling, paper workspace, revisions, marking arithmetic and qualified evidence contracts in same spec. Product implementation NOT RUN. |
| NEXT_SAFE_IMPLEMENTATION_GATE | BLOCKED | B1 only after actual complete cross-platform development acceptance; production-only unknowns then block migrations, not the no-migration read-only adapter. |

A1 feature publishing provisions CI after local full validation and independent review. It does not certify cross-platform or production readiness in advance.

## Reconciled input/source/runtime ledger

`docs/evidence/gate-a-2026-10-11/input-ledger.json` records input SHA-256 hashes, all 13 substantive/supporting Markdown resources, 48 verified bundle-manifest entries, duplicate comparisons and exact baseline failure IDs. The separate implementation plan and Windows guide are byte-identical to their ZIP versions. The empty `.openai-download-*` entry is not a substitute report. Recovered historical reports were used for the A–J/A–G reconciliation and source contracts, without replaying old gate requirements against an incompatible branch.

`baseline.json` preserves the requested pwd/worktree/status/ref/fetch/log/branches/diff commands and exit codes. Remote main matched the pinned SHA on re-fetch. Isolated linked worktree is `/workspace/scratch/d0cf2cf43224/gate-a`, separate from the clone main worktree. No pre-existing personal checkout/vault was used. Pure CRLF `backup.py`/`dashboard.py` blob differences were resolved with local Git info attributes; no source normalization or cleanliness waiver. Seven historical branches were inspected read-only; none were merged or cherry-picked.

| Branch | SHA | Ahead | Behind |
|---|---|---:|---:|
| anvaya/library-read-model-phase-a | `94c75759e7489af302ba43df1e1e6e7b944520b1` | 1 | 4 |
| anvaya/operational-ux-integrations | `6f02b1eb9b3d8fb45f3fec0aa3ef062d81afab94` | 39 | 330 |
| anvaya/tutor-2.0 | `c4b2b9a9ec54d3c046c8be744a01c3e5d04e0711` | 86 | 330 |
| anvaya/tutor-2.1-adaptive-intelligence | `76be911c01b5a6e526f4a38e0bc3722c8f8887f7` | 151 | 330 |
| anvaya/tutor-2.2-student-model | `8c65f661c2a5c031a693c43836af5f6dae69bf77` | 212 | 330 |
| anvaya/tutor-2.3-teaching-orchestration | `7fd24eb6695d7e1a904494756aa333fee274427b` | 322 | 198 |
| anvaya/assessment-uc100n-coding-helper-2 | `9db42382ae617e6df52e31c9d9faa01bf517c871` | 0 | 1 |

Local tested runtime: Python 3.12.14, SQLite 3.53.1, Node 24.19.0, Flask 3.1.2, pytest 9.1.1, numpy 2.4.6, pandas 2.3.3, matplotlib 3.10.9, Playwright 1.51.0, tzdata 2026.2. CI pins Python 3.12 and Node 22, and records actual patch/runtime/package versions in each job. Test-only scientific and Windows timezone dependencies are in requirements-dev; production requirements unchanged.

## Original failures and actual repair

Unmodified fresh source reproduced exactly **1681 passed, 17 failed, 1 module skipped**, exit 1. Raw `baseline-full.log` and XML are byte-preserved in gzip files under the evidence directory; compression avoids treating original pytest whitespace as new source whitespace. Browser import skip occurred before browser requirements were installed; it is not retained as a green shortcut. Sixteen failures required a root production DB. Scoped fixtures now apply actual migrations to a newly allocated temporary DB with deterministic course, topic, retrieval and Tutor session data. Existing Flask service factories inject real services/repositories. Existing assertions, including historic root-no-DB/import safety, remain. No global root DB, fabricated config env override or conditional empty-session skip.

The seventeenth failure was the Coding Helper executable card test importing undeclared Pandas/Matplotlib. Those exact tested compatible packages are now declared as development requirements. The original card test is unchanged and passes. No baseline failure is unresolved.

Exact failure IDs:

- `tests.test_assessment_coding_helper_2::test_all_card_examples_compile_and_run_with_synthetic_data`
- `tests.test_phase7_5_academic_agent_web::test_tutor_repository_lists_recent_sessions_newest_first`
- `tests.test_phase7_5_academic_agent_web::test_tutor_repository_rejects_unbounded_session_limit`
- `tests.test_phase7_5_academic_agent_web::test_workspace_lists_courses_sessions_and_provider_status`
- `tests.test_phase7_5_academic_agent_web::test_workspace_unknown_course_is_safe_and_does_not_call_provider_complete`
- `tests.test_phase7_5_academic_agent_web::test_create_session_defaults_to_source_only_and_reopens`
- `tests.test_phase7_5_academic_agent_web::test_create_session_accepts_source_first_and_keeps_scope_immutable`
- `tests.test_phase7_5_academic_agent_web::test_create_session_rejects_invalid_mode_policy_and_course`
- `tests.test_phase7_5_academic_agent_web::test_session_view_missing_session_is_safe_404_boundary`
- `tests.test_phase7_5_academic_agent_web::test_ask_persists_grounded_exchange_and_only_tutor_tables_change`
- `tests.test_phase7_5_academic_agent_web::test_ask_rejects_blank_question_without_turns`
- `tests.test_phase7_5_academic_agent_web::test_provider_unavailable_is_safe_and_does_not_persist_normal_turns`
- `tests.test_phase7_5_academic_agent_web::test_provider_request_failure_is_safe_and_does_not_persist_normal_turns`
- `tests.test_phase7_5_academic_agent_web::test_insufficient_evidence_persists_bounded_response_without_provider_call`
- `tests.test_phase7_5_academic_agent_web::test_real_agent_get_does_not_change_production_database_or_retrieval_index`
- `tests.test_phase7_5_academic_agent_web::test_real_session_get_is_read_only_when_a_session_exists`
- `tests.test_phase7_5_anvaya_shell::test_existing_phase75_get_routes_keep_working`

Test counts differ for documented reasons: the original 1698 runnable tests now pass; installing Playwright enables 34 existing browser tests; new harness/collector/fixture/characterization/browser tests add coverage (31 at run-62m06053, then one collector race regression). No -k/deselection/blanket skip/assertion removal. A new suite may fail when a known product defect changes; its reproduction must then be replaced by the owning desired-behavior acceptance test, not muted.

## Validator and CI behavior

Install tracked requirements in a disposable environment and Chromium (`python -m playwright install --with-deps chromium` on Linux; `python -m playwright install chromium` on Windows). From the feature checkout run:

`python scripts/architecture_validation.py --output <new-or-validator-owned-directory-outside-repo>`

PowerShell: `powershell -NoProfile -File .\scripts\architecture_validation.ps1 -Python <test-python>`.

The required explicit external output refuses source/ancestor/symlink/non-owned roots. Repeated owned runs keep separate immutable evidence directories. Export uses only Git's tracked/staged inventory and excludes root data/index/control/.env; untracked documents/test databases/credentials are never inferred as feature files. Stage explicitly reviewed new files before precommit validation. Snapshot manifests capture source HEAD, dirty state, each file hash and fingerprint. A fresh Git snapshot supports existing source-bound tests. No live database/control/vault/provider configuration is copied. Runtime whitelist removes provider credentials; Python sockets are restricted to loopback. Tests use explicit temporary DB/service factories and deterministic providers/clocks. No paid/live provider evaluation was run; educational provider quality remains NOT RUN.

Commands include unchanged full pytest, original five-file focused set, both agent/shell/Phase2 orders, portable characterizations, original+new real headless Chromium, Node with Python-expanded filenames, pip check/freeze, compile, synthetic migrations twice with exact ledger/checksums, integrity/FKs, logical read state and DB/WAL/SHM effects, source and feature working/staged diff checks. Any failed/error/skipped/empty pytest run cannot produce platform PASS. Logs/XML preserve all failures. Setup errors remain BLOCKED. Per-command cwd/environment policy and whole-validator replay are recorded.

Workflow `.github/workflows/architecture-validation.yml` runs on relevant feature pushes, PRs and dispatch. Ubuntu/Windows matrix has no continue-on-error, installs fresh browser, and preserves source-SHA logs/XML/screenshots/manifests even on failure. Private fixture DB files and exported source are excluded from artifact uploads. Aggregate acceptance depends on both matrix jobs and publishes source-linked PASS only for matrix success, while production authority stays BLOCKED. Historical feature-specific workflows were not rewritten.

Actual new browser assertions cover 390/768/1366/1920 widths, overflow, keyboard Space/focus/input autosave, 200% CSS reflow and control reachability, browser close/reopen and actual server restart on the same persisted session with injected clock, remaining wall-time/state, and intercepted external requests. Original 34 browser tests still run. Screenshot artifacts support assertions. These are current timer/reopen baselines, not a claim true Pause or paper marking is implemented.

Local fresh Chromium download attempts failed with corrupt archive/lock errors. Local green runs used an already complete Playwright browser cache after actual launch/version verification (Chromium 134.0.6998.35). That limitation is retained; CI's browser installs are fresh and must succeed independently.

## Characterization versus product acceptance

| Finding | Reproduction | Desired product behavior | Repair owner / future acceptance ID |
|---|---|---|---|
| A strong score creates recovery | PASS | FAIL | C / test_strong_topic_has_no_automatic_recovery_candidate |
| B Oct30 preferred task scheduled Oct1 | PASS | FAIL | E / test_future_preferred_date_not_selected_early |
| C GET creates missing legacy JSON | PASS | FAIL | B / test_get_missing_legacy_files_does_not_create_files |
| D mapping trust not snapshotted | PASS | FAIL | B / test_unknown_snapshot_mapping_is_excluded |
| P01 saved/proposed primary view | PASS | FAIL | E / test_approved_day_primary_view_uses_saved_items_and_totals |
| P02 duplicate deadline work | PASS | FAIL | E / test_task_deadline_is_marker_not_fixed_routine_or_duplicate_work |
| P03 dropped rollover reappears | PASS | FAIL | E / test_tomorrow_respects_reviewed_rollover_decisions |
| P04 recurrence COUNT restart | PASS | FAIL | E / test_count_recurrence_day_week_month_equal_filtered_global_series |
| P05 recurring class omitted | PASS | FAIL | E / test_recurring_event_with_end_time_survives_later_window |
| P06 month revision collision | PASS | FAIL | E / test_changed_month_revision_preserves_history_and_updates_owned_entities |
| P07 1080 selected versus 540 reported | PASS | FAIL | E / test_saved_study_and_tasks_share_total_capacity_and_deep_limit |
| P08 completion lacks engagement | PASS | FAIL | E / test_completion_creates_one_engagement_and_suppresses_completed_source |

Reproduction scripts execute only inspected disposable source/DB/JSON copies. Read previews retain SQL logical state; legacy GET file creation is explicitly reported as a known defect. They do not normalize away current effects. Test XML records owner/future IDs.

## Minimal Windows release-only work

Run the new collector with actual launcher Python and exact installed checkout:

```powershell
& $LivePython .\scripts\architecture_local_collector.py --repo $Repo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Default performs identity/control metadata only, with no DB connection/copy. Optional `--closed-no-writers` requires explicit shutdown/backup/sync attestation and conservative Windows process evidence. Only then copies DB+existing WAL/SHM locally; checks source hashes both after copy and after inspection; query-only opens the copy (not immutable, so WAL is interpreted); checks source migration ledger, required schema, integrity/FKs and projection key inventory; deletes private copy. Output has no academic rows, personal paths, secrets or vault. Presence of projection keys does not prove parity; launcher/projection local review remains BLOCKED. Synthetic tests prove no-access default, redaction/source preservation, symlink refusal and rejection of a writer that starts during inspection.

Only remaining manual facts: actual launcher/checkout/interpreter identity; closed stable schema/backend/projection parity; brief real-user approved-release smoke. No production collector was run here, no real DB is requested for cloud upload, and no repeated Windows regression/screenshot session is required.

## Assessment and subsequent implementation

`ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md` defines true policy-controlled practice Pause with active-time accounting, server-authoritative expiry, same attempt identity, autosave acknowledgments, concurrency/idempotency, restart/two-tab races and guarded compatibility readers. Exam pause is disabled except explicit snapshotted accommodation. Additive execution extension must be gated on real schema lineage; old active attempts require explicit adoption, not silent rewrite.

Paper subjective workflow uses same workspace/package: paper solving, explicit finish, per-question private marking guide, human-authored structured rubric inside compatible v1 string, graceful plain-prose fallback, per-step/question marks, exact decimal arithmetic, incomplete drafts, explicit final confirmation and immutable correction revisions. Typed self_reported/self_assessed source stays out of official evaluation confirmation, independent mastery and v1 recovery. Unknown topic mappings remain visible/qualified and excluded. No scans/OCR/AI grading required. No migration/product UI was implemented under A1.

Versioned addendum preserves recovery thresholds exactly and puts AP pause after its schema authority, PS self-grade after B provenance authority, and C/D/E/F/G in original dependency order. B1 is limited to explicit existing-DB read-only canonical DTO adapter, retaining unknown historical mapping/independence, source IDs, no consumers/writes/schema/backfill. Its implementation is conditional on actual cross-platform dev green; production schema unknown blocks only later migrations.

## Review and final execution evidence

Independent whole-delta reviewer inspected code, designs, original contracts, strict XML and synthetic tests. Review identified broad untracked export and single-platform/aggregate naming; both repaired. Export regression was RED then GREEN; collector writer-during-inspection regression RED then GREEN. Reviewer confirmation, final validator path/counts, publishing result and next gate are appended below after execution. No merge/deployment is authorized.

Final precommit Linux run: `run-ix7dlryp`, source snapshot `663cff2d5fb01764918b59261929413f2aaf4b59`, fingerprint `300830b3b0c8f5f3bd7ad14b190ec0df2ab498adad0aab235ec30221e44bac53`. **1764 full pytest PASS**, focused54, both orders41each, characterization13, headless39, Node20; all other15-category checksPASS, no skips/failures/errors. Per-platformPASS, cross-platformBLOCKED. `linux-final-summary.json` and independent review record preserve category/runtime/command evidence.

Precommit source SHA is baseline with staged feature delta; snapshot fingerprint identifies tested implementation bytes rather than falsely claiming baseline alone was tested. Final compression of byte-preserved baseline evidence and report/review text occurred after snapshot export; implementation/test/workflow bytes are unchanged. Final feature diff checks are clean. Feature publication/CI is attempted after this reviewed green Linux evidence; final session handoff records actual GitHub result and HEAD.
