# PAO final correctness review

Reviewed working tree against `1190440`, including untracked production files and focused new tests, on 12 November 2026. Read-only source review; only this report was written. No full suite run. Disposable reproductions used `pao-venv` and the existing fixture builders; no real owner data touched.

## Important findings

### P1 — First receipt on a legacy agenda discards already recorded minutes

`personal_learning_assistant/repositories/sqlite/planner_execution_repository.py:85–88` replaces agenda `actual_minutes` with the sum of new work-log rows. There is no bridge preserving the pre-existing legacy value. `personal_learning_assistant/services/weekly_evidence_service.py:53–58` subsequently excludes that legacy value as soon as *any* log refers to the agenda item. Reproduced on a migrated disposable fixture: approved open agenda item with legacy `actual_minutes=30`; append a legitimate 10-minute progress log; stored agenda actual becomes **10**, not 40, and the old 30 minutes have no durable receipt. Completing without new minutes can similarly overwrite the old value with NULL. This violates WP2's preservation/deduplication contract and understates weekly effort. Preserve proven legacy effort through a unique origin bridge before replacing the projection; do not simply add legacy totals on every command.

### P1 — First manifest activation strands existing path-scoped study history

`personal_learning_assistant/services/obsidian_manifest_service.py:27–28` assigns a fresh item UUID when there is no prior manifest; `personal_learning_assistant/services/study_item_resolver.py:29–35` immediately switches all reads/writes to that UUID. No reader fallback or migration maps the previous path-scoped identity. `personal_learning_assistant/repositories/sqlite/obsidian_source_identity_repository.py:17–24` inventories only `assistant:%`, so ordinary notes' `path:%` history is neither reconciled nor even reported as unresolved. Reproduced: unchanged `A.md` without assistant ID resolves as `path:<digest>` before `refresh_manifest()` and `obsidian-source:<new UUID>` afterward. Existing key points, doubts, sessions and history remain stored but disappear from the note reader. This applies to the first refresh of an existing connection and reconnect/activation flows. WP3 requires provable one-to-one reconciliation and a visible unresolved legacy view; preserve/map old ownership where justified, and expose the rest rather than silently hiding it.

### P2 — User-facing folder relocation has no identity-preserving operation

`personal_learning_assistant/services/obsidian_workspace_service.py:512–514` creates a fresh connection UUID and manifest on every `connect_vault`, including selecting the same folder again or its relocated copy. `refresh_manifest` can only use the already configured path. The relocation test changes config directly, bypassing this command. A user moving/restoring a folder through connection settings loses access to its existing study identity/history. WP3's “Root relocation changes locator only” is therefore not implemented through the product workflow. Add an explicit relocate command binding the current connection and checked destination, keeping Replace connection distinct.

## Boundaries checked / remaining scope

The new execution transaction checks command replay before current revision, locks task and agenda state together, and checks canonical update row count; no further critical archive/replay defect was found in that path. Optional activation is explicit and read adapters use read-only connections; no new startup/GET migration was found in the reviewed paths. Closed weekly reviews read saved evidence JSON rather than recomputing totals. Durable proposal context is stored in the same draft transaction and approval rechecks the day fingerprint; no restart-loss defect was found with PAO enabled. Duplicate external IDs block companion writes and source UUIDs isolate connections after manifest creation.

These observations are not a claim that WP0–WP8 acceptance is complete. Browser journeys, interruption/restore/rollback proof, complete legacy reconciliation and user-visible unresolved history, corrections after agenda closure, all source-to-study interactions, and the full WP8 fidelity/transfer matrix were not comprehensively verified here. Blueprint metrics explicitly left unavailable (revision queue and weekly comparison) also remain unfinished requirements rather than completed metrics. Parent verification owns suite/browser evidence.

## Resolution and final integration

- P1 legacy minutes: fixed with a unique `legacy-agenda:<item>` work-log bridge before adopting projections; missing historical timestamps block ambiguous adoption. Regression confirms 15 legacy + 10 new minutes = 25, then a superseding correction = 23 without altering original completion timestamps. Completion without entered new minutes also preserves the legacy total.
- P1 path history: first manifest records a qualified prior-path reference. Reader exposes earlier annotations/history read-only while new writes use stable UUIDs; bare external UUIDs are never adopted. Renames/refreshes retain that reference. Regression creates a pre-manifest key point and confirms it is still visible afterward.
- P2 relocation: explicit guarded product action checks the existing connection ID and all manifest path/hash pairs, then changes locator only. A changed destination is refused without changing config.
- Additional integration: source-linked queue and covered adjacent-week comparisons now implemented, Learning and Obsidian source-to-task preview paths carry exact revisions/hashes, and shared descriptor reads guard ingestion as well as browsing.

The final validation report records the post-fix suite and browser checks. The original findings remain above as the review record; they are not open blockers after these verified fixes.
