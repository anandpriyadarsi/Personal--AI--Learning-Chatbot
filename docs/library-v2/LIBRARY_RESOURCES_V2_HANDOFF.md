# ANVAYA Library & Resources V2 — isolated handoff (19 October 2026)

## Isolation
- Feature branch: feature/library-hub-resources-v2-2026-10-19
- Verified base main c7998c113f9c7e36e00fcf5274bd79a60b486eb1
- Independent from Architecture V2.2, Learning, Assessment, Planning, and other workstreams.
- No merge, deployment, migration, local academic import, course source mutation, or personal data access.

## Implemented
- Adapted immutable Phase A Library model/repository/service from preserved donor branch.
- GET /library and GET /library/resources/<resource_id>, canonical filtering/pagination, safe document-reader links and accurate unavailable/empty states.
- Workspace V2 navigation with config-controlled Library visibility.
- Resources page redesigned with responsive dark-theme hero, progress metrics, filters, resource cards, status pills, safer readable links and existing add/update forms.
- Scoped visual system in library.css. No global app.css changes.
- Canonical Library and legacy Resources stay distinct: no hidden migration or automatic import. Source files, native Notes, Obsidian, Tutor, Assessment, Planning and Learning Studio are untouched.
- Live SQLite WAL: fail closed without a valid owner snapshot. When supplied by the normal launcher, reuse the authorized Planning/Analysis owner snapshot and deserialize read-only to RAM. No Library GET opens the live SQLite WAL or SHM.
- Feature flag ANVAYA_LIBRARY_ENABLED=false; optional path ANVAYA_LIBRARY_DATABASE_PATH; service factory injection retained.

## Final development (19 October 2026)
- Library adds literal Unicode case-insensitive title/provider/type search, composed with existing course/kind filters before pagination. No document body or private path search.
- Independent review reproduced a DELETE-to-WAL race. Library now captures a bounded stable DELETE-mode file image, validates file descriptor/path stamps and sidecars, then queries only a RAM copy. Live WAL still requires the existing authorized owner publisher. Captures over the existing 128 MiB snapshot limit fail closed.
- Document labels discard URI authority/query/fragment credentials before choosing a basename. No source pathname is opened by resource IDs or search input.
- Source-reader actions require matching Library/Knowledge database identity. A custom Library source with a different or opaque reader displays an unavailable action rather than forwarding colliding IDs to another source. Existing Knowledge reader behavior is unchanged.
- Resources has a more compact header, clearer rectangular cards, aligned mobile status controls, reduced mobile metadata, visible keyboard focus, and keyboard activation that focuses the existing title field. Native details fallback is retained.
- Final acceptance workflow checks out the exact PR head, records head/tree/platform, enforces zero focused skips and rejects every full-suite skip outside the four named external IKS prerequisite tests. No private pilot fixtures are included or imported.
- Final execution report and GitHub Actions results are the authority for final head, test totals and merge status; earlier pending/historical entries below describe the original handoff.

## Validation
- Original isolated Phase A branch reported 109 focused passed and Windows checks; this is historical, not verification for this branch.
- New focused tests cover grouping, filters, privacy, XSS, zero writes, WAL no-publisher fail-closed, owner-snapshot reading, stale/foreign rejected snapshots.
- Real Chromium Library index/detail responsive checks at 320/390/768/1366/1920 and screenshot capture at 390/1366.
- Dedicated GitHub Actions Ubuntu/Windows workflow includes existing Resources UI journeys, source preservation, protected surfaces and whole-project pytest, with JUnit/log/screenshot artifacts.
- Final branch exact-head CI and independent visual/engineering review are PENDING until results are available. Known four external IKS pilot skips cannot be called a strict architecture pass.

## Review gates
1. Check exact-head Linux and Windows CI; fix failures without suppressing assertions.
2. Review both Library and Resources screenshots, keyboard/no-JS access, long text and mobile overflow.
3. Preserve existing records and protected studios through integration.
4. Reconcile with latest main and Architecture V2.2 before any later authorized merge.
5. Do not merge to main or deploy without explicit user instruction.

## Deferred intentionally
Controlled source import; cross-authority Notes/Obsidian integration; rich document thumbnails; material upload; resource version/history; advanced source reader; automatic Tutor/Planning/assessment inference.
