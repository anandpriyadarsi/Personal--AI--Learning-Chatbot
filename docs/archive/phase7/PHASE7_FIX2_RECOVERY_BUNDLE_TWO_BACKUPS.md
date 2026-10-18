# Phase 7.2 — Recovery Bundle + Two Verified Backups

## Starting point

Phase 7.2 starts from the completed Phase 7.1 inventory commit:

`31d5783d6ddb7740ab40b146f645f9c9439f5d2a`

Branch:

`phase7/deprecation-observation`

No retirement/deletion is permitted in this unit.

## Objective

Before Phase 7 observes or retires legacy consumers, the modern system needs a
recovery representation stronger than the historical `backup.py`.

The historical helper only copies legacy `notes.json` / `resources.json`.
Phase 7.2 instead protects the post-Phase-6 authority boundary.

It creates **two independently built and independently verified backup
directories** from one stable source snapshot.

## Recovery pair contents

Each backup contains:

```text
backup-A/ or backup-B/
├── sqlite/
│   └── learning_assistant.db
├── control/
│   └── phase4_authority.json
├── legacy_json/
│   └── known safe compatibility/migration evidence when present
├── vaults/
│   └── registered note bodies whose registered vault roots are available
├── sources/
│   └── registered local source bytes only when an explicit source root is supplied
├── manifests/
│   ├── migrations.json
│   ├── vaults.json
│   ├── sources.json
│   ├── runtime_inventory.json
│   ├── git_identity.json
│   ├── exclusions.json
│   └── recovery_contract.json
└── recovery_manifest.json
```

The pair root also contains:

```text
pair_manifest.json
```

## SQLite safety

The authoritative database is never copied with a raw filesystem copy.

Each backup uses `sqlite3.Connection.backup()` independently.

Each resulting SQLite file must pass:

```text
PRAGMA integrity_check == ok
PRAGMA foreign_key_check == empty
migration prefix == 0001/0002/0003/0004
```

A deterministic logical SQLite fingerprint is computed from schema + sorted
table contents.

Backup A and Backup B must have the same logical fingerprint and the same
source-snapshot identity.

Raw SQLite hashes are recorded for per-bundle tamper verification but are not
used to require byte-for-byte equality between independent online backups.

## Stable source snapshot

The pair creation captures source identity before A, again before B, and once
more after B.

If any authoritative/source identity changes during pair creation, the whole
operation fails and its unique staging directory is removed.

The requested output directory is installed only after both backups verify.

Existing output is never overwritten.

## Vault note bodies

`vaults.root_path + note_metadata.relative_path` is used only locally to read
registered Markdown.

Absolute vault paths are **not written into recovery manifests**.

For every registered note, the manifest records:

- vault/note stable IDs;
- portable relative path;
- registered source hash;
- current actual hash when available;
- whether registry hash matches;
- archived/trashed/active state;
- backup-relative path when copied.

A missing/unavailable external vault is represented honestly instead of being
silently fabricated.

Phase 7.3 will decide whether an external dependency prevents a complete
restore rehearsal.

## Registered knowledge sources

SQLite stores portable `knowledge_documents.path_key` values, not the physical
root path. Therefore Phase 7.2 never guesses a source root.

An operator may explicitly provide:

```powershell
--source-root project-documents=.
--source-root lectures=D:\Academic\Lectures
```

When a root is supplied:

- path traversal is rejected;
- symlink traversal is rejected;
- bytes are SHA-256 checked against the registered `content_hash`;
- the copied bytes are independently hashed.

When a root is not supplied, the source remains represented by its registered
hash/provenance as an external dependency.

Public `http` / `https` canonical provenance may be preserved. Local absolute
URIs are not written into the portable manifest.

## Secret-sensitive exclusions

Generic registered source paths matching credential/runtime patterns are never
copied, including examples such as:

```text
.env
.env.*
credentials*.json
*.pem
*.key
*.p12
*.pfx
*api_key*
*access_token*
*refresh_token*
*private_key*
*client_secret*
```

The bundle also never recursively copies:

```text
.git
.venv
venv
__pycache__
.pytest_cache
.phase5_retrieval
node_modules
```

The Phase 5.8 retrieval index is explicitly derived/rebuildable state.

It is represented by policy, not backed up as authority.

## Legacy JSON evidence

Only the explicit known compatibility/migration evidence list is eligible:

```text
courses.json
assessments.json
assessment_workspace.json
learning_memory.json
course_progress_history.json
weekly_study_plans.json
multi_course_weekly_plans.json
intelligent_study_plans.json
semester_grade_config.json
notes.json
resources.json
obsidian_config.json
```

Unknown `data/*.json` files are not swept into the backup.

This prevents a broad backup routine from accidentally packaging unrelated
credential/runtime JSON.

## Phase 7.1 ledger

Every bundle stores a freshly generated Phase 7.1 static runtime inventory.

That gives later restore/retirement work the exact compatibility-consumer
evidence that existed when the backup was created.

## Preview

Preview is read-only:

```powershell
python .\phase7_recovery_bundle.py preview `
  --project-root . `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json
```

It reports required source-root keys so the operator can choose which external
source roots to include.

## Creation

The retained output must:

- not already exist;
- be outside the repository;
- not overlap a registered source/vault root;
- have a name clearly containing `phase7` and `recovery` or `backup`.

Example:

```powershell
python .\phase7_recovery_bundle.py create `
  --project-root . `
  --database .\data\learning_assistant.db `
  --authority .\.phase4_authority.json `
  --output ..\phase7-recovery-2026-09-16 `
  --source-root project-documents=. `
  --confirm CREATE_PHASE7_TWO_VERIFIED_BACKUPS
```

Source-root flags are optional. Unprovided roots remain explicit external
dependencies in the manifests.

## Verification

Any retained pair can be independently reverified:

```powershell
python .\phase7_recovery_bundle.py verify `
  --bundle-root ..\phase7-recovery-2026-09-16
```

Verification hashes every declared payload again and re-runs SQLite
integrity/FK/logical checks on both backup databases.

## No restore yet

Every bundle and pair manifest explicitly records:

```text
restore_performed = false
phase7_3_restore_rehearsal_required = true
```

Phase 7.2 does not restore, import, replace, promote or mutate production data.

That boundary belongs to Phase 7.3.

## Gate behavior

`phase7_fix2_gate.ps1` creates a complete A/B recovery pair in a unique
temporary directory outside the repository, independently verifies it, then
removes only that temporary output.

The gate does not create the retained long-term backup pair.

After the gate passes, create one retained pair with the operator CLI before
committing Phase 7.2.

## Next boundary

Phase 7.3 — Full Restore + Reverse-Restore Rehearsal.

That phase must consume a verified retained Phase 7.2 pair and prove recovery
entirely in isolated temporary directories.
