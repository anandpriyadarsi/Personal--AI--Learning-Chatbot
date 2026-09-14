# Phase 4.4 — Question Topic Mappings SQLite Dual-Read Foundation

## Purpose and authority boundary

Phase 4.4 promotes the relationship that Phase 4.3 explicitly deferred:
`question_topic_mappings`. The exact base is Phase 4.3 commit `eb53aee` on
`phase4/structured-cutover`.

Legacy `data/assessment_workspace.json` remains authoritative for application-
visible topic tags and `topic_mapping` objects. SQLite remains observation-only.
There is no SQLite-authoritative mode, no dual write, no production database
opened implicitly, and `automatic_topic_mapping.py` is not rewired.

## Repository seam

Phase 4.4 adds:

- `SQLiteQuestionTopicMappingRepository`, which reads Phase 3 relational mapping
  rows and exact migration-ledger evidence without writing;
- `QuestionTopicMappingBackendConfig` with only `legacy` and `dual_read`;
- `DualReadQuestionTopicMappingRepository`, which always returns/saves through
  the legacy workspace repository and records independent SQLite diagnostics;
- focused semantic comparison for raw topic evidence, relational ownership,
  target-course integrity, source hash/version, unresolved candidates, and stale
  or unexplained mapping rows.

## Evidence contract

The Phase 3 Fix 7 importer remains the definition of imported evidence. Phase
4.4 does **not** rerun `automatic_topic_mapping.py`, recompute similarity scores,
or silently accept a proposed candidate. Instead it consumes:

- `question_topic_mapping_observation` ledger entries containing exact
  `raw_topic`, exact `raw_topic_mapping`, and candidate resolution results;
- `question_topic_mapping` ledger entries for candidates that resolved to one
  imported topic in the assessment course;
- actual `question_topic_mappings` rows and their `questions` / `topics`
  relationships.

Unresolved or ambiguous labels remain review-required. No foreign key is guessed.

## Safety

Every SQLite parity read verifies `connection.total_changes` is unchanged.
SQLite writes through the Phase 4.4 adapter raise a read-only error. Dual-read
save operations still call only the legacy JSON repository.

## Deferred domains

Phase 4.4 does not cut over attempts, mistakes, assessment performance, learning
memory/progress, study plans, grades, calendar, Notes/Resources, knowledge/RAG,
Obsidian, dashboards, or Phase 5 work. Those remain later Phase 4 units.

## Verification

Run before committing Phase 4.4 work:

```powershell
.\phase4_fix4_gate.ps1
```

The gate requires branch `phase4/structured-cutover`, base HEAD `eb53aee`, only
Phase 4.4-scoped working-tree changes, all Phase 4.1–4.3 regressions, all Phase 3
tests, the full suite, compileall, pip check, `git diff --check`, and repository
hygiene checks.
