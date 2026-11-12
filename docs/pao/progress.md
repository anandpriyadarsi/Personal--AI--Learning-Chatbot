# PAO implementation ledger — docs/pao/blueprint.md

Base1190440; spec docs/pao/audit.md. WP0–WP8 implemented in this branch; WP9 optional excluded. Dedicated checkout; synthetic data only.

- WP0 baseline:158 existing tests passed before implementation; dependencies pinned in a disposable local environment.
- WP1: missing guards/truncated1001 import reproduced RED, corrected GREEN; raw collection shapes and scoped/expired/origin/host rejection tests. Shared source boundary includes ingestion-root/file symlink regression.
- WP2: changed-import reopening and archived/duplicate completion reproduced RED, corrected GREEN; revisions, receipt replay, partials, correction, legacy bridge, backup/retry/rollback regressions.
- WP3/WP8: connection collisions, duplicate hints, code rewriting, missing manifest and whole-vault heartbeat reproduced RED; identity/manifest/reader/transfer suite GREEN; explicit relocation and earlier path-history review regressions corrected.
- WP4/WP7: historical weekly totals, frozen snapshots, editable source intents and context-bound actions tested. Queue/comparison and Obsidian study preview additional RED→GREEN.
- WP5: capture/course ownership/timing/lifecycle tests; legal forms and preserved values/filters.
- WP6: durable multi-window context, restart, relevant-source staleness, feasible selection/review queue, rollback and duplicate save checks.
- Review: docs/pao/final-review.md; all three findings fixed and regression-tested.

Ruling: use fresh isolated feature checkout, preserving the original working-copy line-ending differences in backup.py/dashboard.py outside this change.
Ruling: manifest/config owns portable source projection; optional0019 owns conservative reconciliation receipts. This reuses the existing atomic configuration backup lifecycle rather than adding a second vault registry owner.
Ruling: retain ambiguous bare UUID histories as unresolved; expose provable qualified path history read-only instead of silently reassigning records. No personal histories were migrated in this session.
Ruling: no optional WP9, Android, public deployment or merge. Changes prepared for review; actual personal-store activation remains explicit.

Final combined verification:557 passed in120.91s, no failures/skips, including50 real browser cases. Post-review clock precision regression corrected; the original broad browser timing failure is recorded in verification.md. No code changes after this passing run.
