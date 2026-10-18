# Phase 7.3 — Full Restore + Reverse-Restore Rehearsal

## Starting point

Phase 7.3 starts from the completed Phase 7.2 commit:

`13ba4589502d03dbed34d55c0e1210e91a3a3cce`

Branch:

`phase7/deprecation-observation`

The retained Phase 7.2 pair is an operator input. It is **not** committed to
Git and Phase 7.3 never edits it.

## Objective

Phase 7.2 proved that two independently created recovery bundles are readable
and internally valid.

Phase 7.3 now proves that those bundles can actually reconstruct an isolated
modern runtime and that the restored SQLite state can still perform the
historical Phase 3 reverse-export/re-import recovery path.

This is a rehearsal only.

It must not touch:

- production `data/learning_assistant.db`;
- `.phase4_authority.json`;
- the live configured Markdown/Obsidian vault;
- live registered source directories;
- `.phase5_retrieval`;
- legacy JSON;
- the retained Phase 7.2 backup pair.

## Retained-pair SQLite isolation

The retained Phase 7.2 pair is treated as immutable evidence.

Before opening either backup database with SQLite, Phase 7.3:

1. hashes the complete retained pair;
2. copies it byte-for-byte into the unique isolated rehearsal staging area;
3. verifies the copied pair;
4. performs all SQLite reads/online restores from that isolated copy.

This is important on Windows because SQLite can create transient journal/WAL
sidecar files beside a database even when the caller intends only verification.
Those sidecars must never appear inside the retained recovery pair.

The temporary pair copy is deleted before a successful rehearsal is published.

## Two independent full restores

Backup A and Backup B are restored independently.

For each bundle Phase 7.3 creates:

```text
restored-A/ or restored-B/
├── state/
│   ├── phase7_restored_[a|b].db
│   └── phase4_authority.json
├── legacy_json/
│   └── restored compatibility evidence
├── vaults/
│   └── restored registered note bodies
├── sources/
│   └── restored registered source bytes
├── provenance/
│   └── recovery metadata + original recovery manifest
├── runtime/
│   ├── phase7_runtime_[a|b].db
│   └── retrieval/
├── phase3-reverse-export/
├── phase3-restore-rehearsal/
└── restored_content_manifest.json
```

The `state/phase7_restored_*.db` copy is the exact restored authority state and
must keep the bundle's logical SQLite fingerprint.

The `runtime/phase7_runtime_*.db` is deliberately separate.

## Portable vault relocation

The backup SQLite contains the historical registered vault root paths. Running
normal code directly against those paths during a restore rehearsal could
accidentally read the user's live vault.

Therefore the exact restored DB is preserved unchanged and a runtime clone is
created.

Only the isolated runtime clone rewrites `vaults.root_path` to:

```text
<isolated restore>/vaults/<vault path key>
```

No note metadata/content is changed.

This proves that a restored runtime can be relocated without using the original
absolute vault location.

## Retrieval rebuild

`.phase5_retrieval` was deliberately excluded from Phase 7.2 because it is
derived state.

For each restored runtime Phase 7.3:

1. reads current `knowledge_chunks`;
2. builds a new lexical Phase 5.8 retrieval generation in the isolated restore;
3. uses no semantic embedding provider;
4. performs a course-scoped MA103N smoke query;
5. requires at least one hit.

Backup A and Backup B must produce the same:

- retrieval source fingerprint;
- chunk count.

The live `.phase5_retrieval` directory is never opened for writing.

## Tutor Workspace smoke

The Phase 6.9 Tutor Workspace opens the restored runtime read-only.

It composes:

- Knowledge Navigator;
- Exam Intelligence;
- Adaptive Mentor;
- Tutor Workspace counts/activity.

The smoke test requires:

```text
provider_called = false
writes_performed = false
mentor.llm_called = false
mentor.authoritative_state_changes = false
```

A deterministic workspace signature is compared between A and B.

## Reverse-export equivalence

Phase 3's `phase3_relational_snapshot.json` is an audit artifact.  It can
contain restore-instance metadata associated with the isolated database
identity/path, so two independently named A/B restores are not required to
produce the same **raw relational-snapshot file hash**.

Phase 7.3 still records that raw hash for each restore, but A/B equivalence uses
a semantic reverse-export fingerprint composed from:

- every exported legacy artifact path/hash/size/record count;
- the Phase 3 logical source-database fingerprint;
- export status;
- reconciliation records;
- documented discrepancies; and
- unmigrated legacy-source declarations.

Therefore A/B may differ in isolation-specific audit metadata while they must
still agree on all recoverable academic state and reverse-export semantics.

## Reverse-restore rehearsal

The exact restored SQLite copy is then passed to the existing Phase 3.2
recovery code.

For each backup Phase 7.3 runs:

```text
restored SQLite
      ↓
reverse_export_phase3(...)
      ↓
legacy JSON compatibility views + relational snapshot
      ↓
rehearse_phase3_restore(...)
      ↓
isolated online backup/restore
      +
fresh migration/re-import DB
      ↓
second migration apply = no-op
second import = zero writes
```

The restored legacy JSON evidence from Phase 7.2 is supplied read-only for
direct reconciliation.

The reverse path may report documented historical differences; it must never
invent or repair them.

The following must pass:

- export SQLite integrity/FKs;
- backup/restore fingerprint equality;
- migration idempotency;
- import idempotency;
- reverse-export hash immutability.

## A/B equivalence

The final Phase 7.3 report requires Backup A and Backup B to agree on:

- exact SQLite logical fingerprint;
- restored content fingerprint;
- retrieval source fingerprint;
- retrieval chunk count;
- Tutor Workspace signature;
- semantic reverse-export signature.

The raw Phase 3 relational-snapshot SHA-256 is retained as audit evidence but
is intentionally not an A/B equality requirement because isolation-specific
database identity metadata is not academic state.

If either independently valid backup restores to a materially different
runtime result, Phase 7.3 blocks.

## Retained-pair immutability

Before rehearsal, every retained-pair file path, byte count, and SHA-256 is
recorded.

The entire retained pair is hashed again after both restorations.

Any byte or file-set change blocks the rehearsal.

## Operator preview

Preview verifies the retained pair and performs no restore:

```powershell
python .\phase7_restore_rehearsal.py preview `
  --recovery-root "C:\Users\91994\Downloads\phase7-recovery-2026-09-16-01"
```

## Rehearsal

Choose a **new absent directory outside both the project and retained pair**:

```powershell
python .\phase7_restore_rehearsal.py rehearse `
  --recovery-root "C:\Users\91994\Downloads\phase7-recovery-2026-09-16-01" `
  --project-root . `
  --work-root "C:\Users\91994\Downloads\phase7-restore-rehearsal-2026-09-16" `
  --course-code MA103N `
  --as-of 2026-09-16 `
  --confirm REHEARSE_PHASE7_FULL_RESTORE
```

The work directory must not already exist.

A failed run removes only its unique staging directory. It never overwrites an
existing requested output.

## Rehearsal report

A successful retained rehearsal contains:

```text
phase7_restore_rehearsal_report.json
```

The report records portable restore-relative evidence and declares:

```text
status = pass
retained_pair_unchanged = true
backups_equivalent = true
restore_performed_only_in_isolation = true
production_or_live_source_accessed = false
semantic_provider_called = false
llm_provider_called = false
retirement_or_deletion_performed = false
```

The report can be checked independently:

```powershell
python .\phase7_restore_rehearsal.py verify-report `
  --work-root "C:\Users\91994\Downloads\phase7-restore-rehearsal-2026-09-16"
```

## No retirement yet

Phase 7.3 does not:

- delete/archive/move a legacy candidate;
- change `main.py`;
- enable runtime consumer logging;
- begin the Phase 7.4 observation clock;
- switch authority;
- apply a production migration.

Successful restore capability is necessary evidence for future retirement, but
it is not itself permission to retire anything.

## Next boundary

Phase 7.4 — Legacy Usage Observation / Consumer Watch.

That phase should add privacy-minimal local observation for compatibility
surfaces and use the Phase 7.1 inventory + Phase 7.2/7.3 recovery evidence as
inputs.
