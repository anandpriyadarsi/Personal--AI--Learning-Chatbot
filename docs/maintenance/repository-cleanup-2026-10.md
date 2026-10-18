# ANVAYA repository cleanup — October 2026

**Branch:** `maintenance/repository-cleanup-2026-10`
**Baseline commit:** `ce2e4e06175f76778f114a85f7552160aeb08a99`
**Status:** Documentation-only archival work, not merged into `main`.

## Verified baseline

The parent tree contained 1,054 tracked files, of which 311 were at repository root (151 Markdown reports and 93 PowerShell gate scripts). The GitHub tree inventory was not truncated.

## Applied cleanup

- 45 historical Phase 3–6 reports moved into `docs/archive/phase3` through `phase6`.
- 33 historical Phase 7 implementation, migration, and recovery reports moved into `docs/archive/phase7`.
- 78 total document renames with unchanged Git blob SHA.
- Documentation landing page, historical index and machine-readable archive manifest added.
- Branch-specific, cross-platform repository hygiene validation provided in `.github/workflows/repository-cleanup.yml`.

No existing application source, academic-data files, migration tools, tests, scripts, dependency manifests, or workflows are moved or deleted by this cleanup phase. A new verification script and new branch-specific workflow are added.

## Deferred cleanup and risk assessment

1. **PowerShell scripts:** The 93 root `*_gate.ps1` scripts may be called manually or via historical automation. Do not relocate before establishing callers and Windows support.
2. **Academic authority and local data:** Never delete production academic databases, local vaults, note assets, learning history or personal backups for file-count reduction.
3. **Tracked backups:** `backup/notes_backup.json` and `backup/resources_backup.json` remain tracked although `.gitignore` excludes the folder. Review provenance, privacy, and consumer references separately before deleting.
4. **Current learning and assessment specifications:** Remain in the root because active parallel branches may reference them by path.
5. **CI workflows:** Current GitHub Actions remain intact. Branch-specific historical workflows require a separate dependency and cost review before consolidation.
6. **Code deduplication:** Defer until imports, dynamic loading, scripts, migrations, and test fixtures can be exercised on Ubuntu and Windows.

## Acceptance

The verification script checks the manifest against Git blob SHA values at the baseline and cleanup head, forbids any unapproved path mutation, checks original root paths are absent, and confirms essential source paths exist. It does **not** prove complete runtime correctness, end-to-end browser behavior, or absence of stale links in third-party systems.

Do not merge without reviewing the GitHub status checks and any unresolved dependency or documentation link findings.
