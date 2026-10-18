# ANVAYA repository cleanup — October 2026

**Branch:** `maintenance/repository-cleanup-2026-10`  
**Parent commit:** `ce2e4e06175f76778f114a85f7552160aeb08a99`  
**Status:** Phase 1, documentation archive only; not merged into `main`.

## Verified baseline

The GitHub tracked-tree inventory on the parent commit contains 1,054 files, 311 root-level files, 151 root-level Markdown documents, 93 root-level `*_gate.ps1` scripts, and 228 files inside `tests/`. The tree is not truncated.

## Changes in this phase

- Relocate 45 historical Phase 3, 4, 5 and 6 Markdown implementation reports to `docs/archive/phase{3,4,5,6}/` using their **unchanged Git blob identifiers**.
- Add an index of the archive and a documentation landing page.
- Do **not** rename or delete code, test fixtures, GitHub Actions, validation scripts, configuration files, private/local academic paths, data migration tools, backups, or branches.

Historical GitHub URLs pointing to root-level report paths must be updated to the new locations. This phase does not prove that every external bookmark is preserved.

## Risk inventory and next phases

1. **Scripts:** root-level `*_gate.ps1` scripts are referenced by previous validation and operational procedures. Inspect all callers and workflows before moving any script.
2. **Tracked backups:** `backup/notes_backup.json` and the empty `backup/resources_backup.json` are tracked even though `backup/` is ignored. Review provenance and retention requirements before removing. Do not rewrite repository history without a separate privacy review.
3. **Local data:** protect academic databases, user notes, vaults, backups, secrets, and learning history. Never use file-count targets as permission to remove these.
4. **Application:** refactor or remove Python modules only with import/reference analysis, migration/restore regression tests and native Windows + Ubuntu validation.
5. **CI:** audit legacy branch-specific workflows separately; do not disable existing gates during active parallel Assessment, Learning Studio and Planning work.
6. **Evidence:** preserve existing test and academic-authority evidence until its consumers and retention needs are assessed.

## Acceptance required before merging

- Source-code path changes are limited to documentation moves and newly added documentation in Phase 1.
- Each moved report has exactly the same blob SHA as before the move.
- The root launcher, package, tests, scripts, workflows and dependency manifests are byte-for-byte unchanged.
- No academic data or production deployment is modified.
- Run available cross-platform regression checks after any later code or entry-point changes. A documentation-only audit is not proof that the full application passes its suite.

The cleanup must remain on a separate branch until independently reviewed. No merge is authorized by this document.
