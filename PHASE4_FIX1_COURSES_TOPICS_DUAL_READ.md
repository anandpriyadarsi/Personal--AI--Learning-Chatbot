# Phase 4.1 — Courses + Topics SQLite Dual-Read Cutover Foundation

## Authority boundary

Phase 4.1 does **not** cut over structured authority.

- Legacy `data/courses.json` remains authoritative for reads returned to callers and for every existing write.
- SQLite is a read-only shadow used only for semantic parity checks.
- `CourseService` keeps its existing public API and still depends on the existing `CourseRepository` shape.
- `main.py` is not modified and no implicit production SQLite path is opened.
- There is intentionally no `sqlite`-authoritative backend mode in Phase 4.1.

This preserves the Phase 3 rollback rule: before structured cutover, a shadow database can be discarded/rebuilt without disabling legacy writers.

## Architecture

`personal_learning_assistant/repositories/sqlite/course_repository.py` adds `SQLiteCourseRepository`.

The adapter reads the Phase 3 schema and reconstructs legacy-semantic Courses/Topics state from:

- `courses`;
- `topics` and `topics.position`;
- `semesters` + `semester_courses`;
- `app_settings.active_course_id`;
- `course_aliases` / `topic_aliases` when present; and
- the latest `data/courses.json` rows in `migration_imports`, which preserve legacy IDs, raw status values, source order, raw topic identities, and other source evidence.

SQLite target IDs are migration-generated and are **not** compared directly with legacy IDs. The migration ledger is the identity bridge.

The adapter rejects `save_state`, document-link upsert, and document-link delete calls. This makes an accidental SQLite write through `CourseService` impossible in this phase.

`personal_learning_assistant/repositories/course_backend.py` adds explicit backend configuration and a factory:

- `legacy` → existing `LegacyJsonCourseRepository`;
- `dual_read` → `DualReadCourseRepository(legacy, sqlite_shadow)`.

In `dual_read`, each read obtains the authoritative legacy result first, independently reads SQLite, creates a structured `CourseParityReport`, and returns the legacy result unchanged. SQLite errors and mismatches become diagnostics; they never replace the authoritative result.

Command/write methods in `DualReadCourseRepository` delegate only to the existing legacy repository. There is no dual-write.

## Parity domains

`load_state` compares:

1. course catalogue (`id`, `code`, `name`, status);
2. active course;
3. legacy semester labels against existing SQLite semester mappings;
4. topics, confidence, and status;
5. course statuses;
6. topic statuses;
7. source course ordering;
8. topic ordering via SQLite `position`;
9. raw course/topic identities and raw import statuses from migration evidence;
10. explicit course aliases;
11. explicit topic aliases;
12. source schema version;
13. structural anomalies such as missing/multiple semester mappings; and
14. course-document relationships where supported.

A diagnostic has a domain, status, severity, optional key, both values, and a message. Mismatches are never converted into matches by sorting, status normalization, or ID substitution.

### Course-document relationship limitation

Phase 3.1 deliberately deferred legacy `courses.json.document_links` instead of inventing a relational mapping. The Phase 4.1 SQLite adapter therefore reports this domain as `deferred` and keeps the legacy relationship authoritative. It does not silently return an empty SQLite relationship as a parity match.

## Safety and testing

The focused test fixture under `tests/fixtures/phase4/` is synthetic. Tests create isolated temporary SQLite databases/fixtures only; no real `data/`, Obsidian, knowledge, or user files are needed.

Focused tests verify:

- SQLite read-contract behavior;
- direct SQLite write rejection;
- legacy-authoritative dual-read results;
- parity across all supported domains;
- explicit topic/status, raw-status, alias, and ordering mismatches;
- explicit deferred document-link diagnostics;
- unchanged legacy bytes after read-only operations;
- unchanged SQLite logical state and `connection.total_changes` after reads;
- `PRAGMA integrity_check` = `ok`;
- empty `PRAGMA foreign_key_check`;
- explicit `legacy` / `dual_read` factory modes only;
- unchanged `CourseService` read API/results; and
- commands continuing to write legacy only, followed by an explicit stale-shadow mismatch.

Run the complete gate with:

```powershell
.\phase4_fix1_gate.ps1
```

The gate runs focused Phase 4.1 tests, all Phase 3 tests, the full regression suite, Python compilation, dependency consistency, `git diff --check`, and repository/scope hygiene checks.

## Non-goals

Phase 4.1 does not begin or modify assessments, questions, attempts/performance, learning memory/progress, study plans, grades/calendar, Notes Studio, Resources 2, RAG, Obsidian migration, Dashboard 2, Phase 5, or `main.py`. It does not disable legacy writers or promote SQLite to sole authority.
