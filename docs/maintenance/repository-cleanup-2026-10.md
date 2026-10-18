# ANVAYA repository cleanup — October 2026

**Branch:** `maintenance/repository-cleanup-2026-10`
**Baseline commit:** `ce2e4e06175f76778f114a85f7552160aeb08a99`
**Status:** Non-destructive dependency-checked cleanup; not merged.

## Findings and work completed

- Inspected an untruncated tracked tree: 1,054 files, 311 root-level files, 151 root-level Markdown documents and 93 root-level PowerShell `*_gate.ps1` scripts.
- Initially proposed archiving 78 historical Phase 3–7 reports. A stronger active-reference check discovered references in existing legacy `*_gate.ps1` scripts. **69 moves were reverted**, retaining their original locations and content.
- **9 unreferenced Phase 3 reports** are now archived byte-for-byte in `docs/archive/phase3/`.
- Added `docs/README.md`, a historical documentation index, an explicit archive manifest and repository audit notes.
- Added a GitHub Actions workflow and Python validator for Windows/Ubuntu that verifies the archive blob identities against baseline, limits the changed-path scope and scans active sources for stale report references.
- No prior application module, test, validation gate, workflow, academic data, backup or dependency manifest is modified by the resulting diff.

## Why the larger document relocation was rolled back

The report names are baked into historical PowerShell validation gates. A pure file move would break those checks. The cleanup leaves all referenced reports in place rather than modifying dozens of gate scripts without a separate dependency audit and Windows compatibility testing.

## Next safe cleanup phases

1. Inventory active versus legacy PowerShell gates and all report/document references, then plan **paired** path updates with Windows execution evidence, or leave them in place.
2. Consolidate active project documentation while keeping Learning Studio, Assessment Studio and Planning/Analysis authority contracts stable.
3. Review tracked `backup/notes_backup.json` and `backup/resources_backup.json` for provenance, local privacy and possible consumers before touching any backups.
4. Do not delete or rewrite history of local academic data, Obsidian vaults, assessment results, notes or credentials.
5. Do not rename production entry points (`phase7_web.py`), migrators, scripts, package files, workflows or tests without targeted regression tests and review.
6. Preserve all active feature branch work and leave `main` untouched.

## Verified and unverified

The branch-specific safety job checks byte-for-byte Git blob identity, unapproved changed paths, stale references inside active code/gates, Python source compilation and Git whitespace hygiene on Ubuntu and Windows.

The safety job is **not** the full integration, browser, migration or local production-authority suite. Require those tests before any change to executable source or before merging the cleanup into `main`.

External bookmarks pointing at relocated report URLs are not automatically redirected.
