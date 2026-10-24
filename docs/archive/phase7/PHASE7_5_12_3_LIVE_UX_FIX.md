# Phase 7.5.12.3 — Live UX Fix

Baseline: Phase 7.5.12.2 recovery commit `fa79195`.

## Purpose

Close issues found during live use without changing the authority model:

1. Unified Study Search must not show a false zero-result state merely because the retrieval index is stale or unavailable.
2. Search should tolerate case differences and common British/American academic spelling variants such as `factorisation` / `factorization`.
3. Obsidian `[[wikilinks]]` should open inside ANVAYA when they resolve safely, and Reader should show backlinks.
4. Operational Calendar should have previous/today/next navigation so October is reachable from September without editing the URL.
5. Dated planner tasks should appear on the Operational Calendar.
6. Existing planner tasks should be editable from the web UI through the existing service boundary.

## Search behaviour

The retrieval index remains authoritative for grounded retrieval and tutor evidence. If it is unavailable or stale, Unified Search degrades to:

- live Obsidian vault matches;
- current SQLite academic metadata matches;
- current extracted knowledge-document chunks for the matched document.

The UI displays a warning when degraded search is used. Source-grounded Ask ANVAYA still requires the stale-safe retrieval runtime and is not weakened.

## Obsidian behaviour

ANVAYA does not rewrite vault Markdown.

Resolved `[[wikilinks]]` are transformed only in the Reader rendering layer. Unresolved or ambiguous links remain visible as their original Markdown text. Backlinks are discovered read-only from the current live vault scan.

## Planner behaviour

Calendar navigation changes only the requested view anchor. Dated tasks are displayed as flexible/all-day task items. Task edits continue through `OperationalPlannerWebService.update_task()`; no direct route-layer SQLite writes are introduced.

## Deferred

This patch does not yet implement:

- recurring-routine creation/editing UI;
- Moodle sync/import;
- ChatGPT/Alex ZIP handoff bridge;
- automatic retrieval-index rebuild;
- automatic Obsidian writes.

Those should follow after this live patch is green.
