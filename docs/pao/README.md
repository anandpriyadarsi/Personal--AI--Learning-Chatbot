# ANVAYA Planning, Analysis and Obsidian implementation

Local web changes on `feature/pao-workflow-v3`, based on main `1190440165ebc11efdb1d87a46a94b092a3344e6` (audit baseline `abe8b3e`). The later main changes are Actions maintenance; no Android, CI or release changes are part of this implementation.

## What changed

| Package | Delivered |
|---|---|
| WP0 | Dedicated checkout/feature branch, synthetic owner databases and baseline checks; audited source and blueprint retained. |
| WP1 | Expiring scoped same-origin command tokens across planner/calendar and legacy/current Obsidian aliases; host checks; raw import shape/cardinality/byte checks; shared bounded non-symlink descriptor reads for reader and ingestion. |
| WP2 | Atomic revision-checked commands, payload-bound replay receipts, terminal-state checks, partial logs, append-only corrections, visible work history, legacy-minute bridge, import preservation and optional additive activation. |
| WP3 | Stable connection/source UUIDs, duplicate-ID write blocking, conservative legacy inventory, read-only earlier path history, explicit rename and verified root relocation, ZIP refresh distinct from Replace. |
| WP4 | Shared scoped evidence envelopes; approved allocated effort; null versus zero; deduped actual logs; historical deadlines independent of agendas; frozen closed snapshots; honest bounded Assessment samples; explicit source study queue; adjacent-week deltas only with matching policy/scope and complete recording. |
| WP5 | Title-first capture; exact active course/topic/assessment validation; legal lifecycle actions; task anchors; retained error values/filters; Today/This Week/Backlog/Exams navigation. |
| WP6 | Multiple explicit availability windows, elapsed/overlap checks, feasibility before cap, visible reason-coded review queue; atomic saved proposal/context revisions; restart recovery and fresh approval tokens. Feature-off retains session-only behavior. |
| WP7 | At most three reviewed suggestions; exact commitment links; editable Learning-source study preview; explicit Obsidian source study preview; source hash/identity revalidation; one intent/one task; immutable task source references and exact server-owned source links. |
| WP8 | Command-owned manifests, selected-note heartbeat reads, one scan per unified search, code/frontmatter link fidelity, relative/wiki/Markdown links and anchors, safe raster images, explicit version-bound copies with copied_from provenance, raw Markdown download and ZIP exclusions. |

WP9 is optional and deliberately excluded: recurring task generation, reminders, managed writeback, ICS/calendar sync and exam-template generation.

No page creates tasks, changes grades, migrates stores, refreshes a source manifest or infers mastery merely by opening it. Tutor/Coding consent and feature flags retain their existing owners. Vault Markdown, Library originals, Notes assets, Assessment marks and Learning attempts remain separate authorities.

## Run on the existing Windows installation

Stop ANVAYA first. Keep your current data; do not replace it with this checkout's synthetic test data. From the repository folder in PowerShell:

```powershell
 git fetch origin
 git switch feature/pao-workflow-v3
 .\.venv\Scripts\Activate.ps1
 python -m pip install -r requirements.txt tzdata==2026.2
 python -m scripts.pao_migrate --database .\data\learning_assistant.db
 python -m scripts.pao_migrate --database .\data\learning_assistant.db --apply
 $env:ANVAYA_PAO_V3_ENABLED = "true"
 $env:ANVAYA_OBSIDIAN_IDENTITY_V3_ENABLED = "true"
 python phase7_web.py
```

If your environment folder is named `venv`, activate that folder instead. If no environment exists, first run `python -m venv .venv`. If the owner database is stored elsewhere, substitute that actual path in both migration commands and retain your installed launcher configuration. Activation refuses a missing database rather than creating an empty academic store. The default launcher serves [http://127.0.0.1:5000](http://127.0.0.1:5000).

Linux/macOS use `source .venv/bin/activate` and `export ANVAYA_PAO_V3_ENABLED=true` before the same Python commands. Windows commands are provided for use on your machine; this Linux verification is not a Windows-runtime pass.

## Backup, activation and rollback

1. Stop all app writers before copying the full existing data/Notes/Library/Learning directories and Obsidian connection configuration using your established backup workflow. The external vault stays independently backed up. A database-only backup is not a backup of every original asset or independent store.
2. Run the migration without `--apply` first. It is read-only and reports contradictory task timestamps and unresolved legacy identities without assigning their ownership. If a live WAL lacks its existing SHM, stop/checkpoint the owner or inspect a verified online backup; do not copy just the main DB file.
3. `--apply` makes a unique SQLite **online backup**, verifies its integrity, and transactionally applies optional 0018/0019 plus checksum records. It does not activate unrelated Assessment/Tutor options. Repeat application is a no-op. Interrupted/failed SQL rolls back; the backup remains available.
4. Enable PAO after readiness succeeds. Existing Obsidian connections should use **Refresh manifest** explicitly; new connections create their own source UUIDs. Earlier qualified path records stay available in a read-only disclosure. Bare external UUID histories remain unresolved in the migration report, never assigned to whichever vault is currently open.
5. To roll back behavior, stop the app and set `ANVAYA_PAO_V3_ENABLED=false`; keep all new tables, receipts and history. Do not restore a pre-migration backup over newer work. Export/reconcile subsequent activity before any deliberate full restore.
6. ZIP Refresh retains connection/source continuity by path; Replace creates a distinct connection. Folder relocation verifies all current manifest path/hash pairs and only changes its locator. Confirm rename requires the old path absent and an exact prior source hash. No source frontmatter is rewritten.

The Obsidian safety/identity fixes apply to normal reader/connection commands independently of optional Planner activation; the identity environment setting is reserved for rollout compatibility and is not a bypass for duplicate/source checks.

## Verification and boundaries

See [verification.md](verification.md), [final-review.md](final-review.md), and [benchmark.json](benchmark.json). Screenshots under `screenshots/` show synthetic records only. Runtime checks use pinned Flask 3.1.2, Mistune 3.3.4, PyYAML 6.0.3, pytest 9.1.1 and Playwright 1.51.0.

Remaining environment checks: actual Windows execution, a physical Galaxy M11, a full screen-reader audit, external Obsidian-app opening and the user's real-data activation. No Windows, Android, personal-data migration or production-provider pass is claimed. Browser reflow was checked at 683 CSS pixels as the equivalent content width of 200% desktop zoom; browser-toolbar zoom and a physical soft keyboard were not separately certified.

Source scope remains explicit: suggestions do not elevate unreviewed Assessment topic mappings into qualified weakness; source-linked study due dates are user commitments, not an inferred forgetting curve. Missing/comparison-incompatible history stays unavailable. All-time Notes inventory and separate Learning projections retain their own disclosed scopes.
