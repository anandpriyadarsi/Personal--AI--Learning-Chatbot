# ANVAYA Operational UX + Integrations

Branch: `anvaya/operational-ux-integrations`  
Baseline: canonical `main` at Phase 7.5.12.3 green commit `f8590ac`.

## Why this branch exists

Live use showed several requests that sounded new but were already implemented.
This branch does **not** rebuild those features.

Already present on the baseline:

- case-insensitive Unified Study Search;
- `factorisation` / `factorization` query equivalence;
- stale-index fallback to current vault/academic metadata;
- resolved Obsidian wikilinks and read-only backlinks;
- previous/today/next calendar navigation;
- dated planner tasks in Operational Calendar;
- task creation and editing;
- month-plan YAML preview/approval;
- recurring-routine persistence/materialization;
- daily agenda generation, approval, tracking, rollover, and weekly review;
- persistent source-grounded Tutor sessions.

## Added here

### 1. Recurring Schedule Editor

The existing `routine_templates` authority is now exposed through a browser UI.

Users can:

- create daily or weekly schedules;
- choose weekdays;
- set active date ranges;
- set start/end time or duration;
- set priority, location, preferred window, and a condition/note;
- edit, pause/resume, or archive schedules.

No parallel scheduling store is introduced.

### 2. Daily Agenda visibility in Calendar

Generated daily-agenda `task`, `study`, and `manual` items are projected into
Operational Calendar views. Fixed academic events/routines continue to come from
their existing authorities, which avoids duplicate calendar rows.

Calendar agenda items link back to the corresponding day workspace.

### 3. Alex / ChatGPT handoff ZIP

From an Obsidian Reader page ANVAYA can create a local ZIP containing:

- `PROMPT.md`;
- `CONTEXT.json`;
- `NITK 2026-30/VAULT_MANIFEST.json`;
- the selected Markdown note;
- optionally, a bounded read-only Markdown snapshot of the connected vault.

The handoff performs **no network request**, does not call an AI provider, and
does not modify the vault. The full-vault export is bounded to 500 Markdown notes
and 32 MiB uncompressed.

Automatic upload to ChatGPT and automatic import of an AI response are not
implemented here.

### 4. Tutor chat UX

The existing Academic Agent / grounded Tutor backend remains authoritative.
Only the conversation presentation is changed:

- ANVAYA/You chat bubbles;
- sticky composer;
- Enter to send, Shift+Enter for newline;
- auto-scroll to newest turn;
- expandable source evidence;
- search-sources and conversation navigation.

No new provider dependency or automatic academic-state mutation is introduced.

### 5. Read-only Moodle connector foundation

Migration `0008_moodle_sync.sql` adds a provenance ledger only. Credentials
are never stored in SQLite.

Runtime configuration:

- `ANVAYA_MOODLE_BASE_URL`
- `ANVAYA_MOODLE_TOKEN`

The connector:

1. reads site/user/course information through Moodle web services;
2. previews supported course files without modifying ANVAYA;
3. explicitly downloads only new/changed supported learning files after the
   user selects Sync;
4. stores them below `knowledge/moodle/`;
5. records Moodle provenance;
6. reuses the existing Phase 5 source registry and extraction pipeline.

Remote Moodle is never modified by this connector. It does not submit
assignments, edit Moodle resources, post grades, or change enrolments.

After successful downloads, the retrieval index is intentionally reported as
needing rebuild; automatic index rebuild is not added in this branch.

## Still deferred

- background/periodic Moodle polling;
- native Moodle notifications;
- assignment submission to Moodle;
- automatic retrieval-index rebuild after sync;
- automatic ChatGPT upload/callback;
- automatic import/write of returned Alex ZIPs into Obsidian;
- autonomous Tutor changes to plans, mastery, grades, or notes.

These require separate safety/authority decisions and are not hidden inside
this UX branch.

## Gate

Run from a clean checkout of this branch:

```powershell
.\anvaya_operational_ux_gate.ps1
```

The gate covers:

- the new schedule, calendar, Alex-handoff, and Moodle tests;
- existing Phase 7.5.12.2/7.5.12.3 search regressions;
- Planner, Obsidian, and grounded-Tutor regressions;
- complete pytest;
- compileall and pip check;
- fresh migrations 0001 through 0008;
- SQLite integrity and foreign-key checks;
- production-data, retrieval-index, and configured-vault hash preservation;
- repository hygiene.

Do not merge this branch into `main` until the gate is green on Anand's local
repository and live browser checks are satisfactory.
