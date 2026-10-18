# Phase 7.1 — Canonical Runtime + Consumer Inventory

## Starting point

Phase 7 begins from the completed Phase 6 closure commit:

`a7566d0026252767a7276ca7ca9df3689e406d61`

Branch:

`phase7/deprecation-observation`

Phase 7.1 is inventory/observation tooling only.

It deletes nothing and changes no authority.

## Why this phase exists

The repository still contains multiple historical surfaces:

- V13 root entry points;
- compatibility facades;
- old planners/dashboards;
- old RAG/retrieval entry points;
- legacy JSON repositories;
- Phase 4 compatibility backends;
- older Academic Agent compatibility routing.

Some of these are still actively used by `main.py`, tests or compatibility
adapters. Others may have no static caller but can still be used manually,
through reflection, subprocesses, user scripts or external integrations.

Therefore:

> zero static consumers is not proof that a file is safe to delete.

Phase 7.1 builds the first machine-readable evidence ledger. Runtime observation
comes later in Phase 7.4.

## Canonical runtime declaration

Phase 7.1 records the post-Phase-6 authority boundaries:

- structured academic authority: `data/learning_assistant.db`
- authority control: `.phase4_authority.json`
- note body authority: configured Markdown/Obsidian vault
- source authority: registered source files
- retrieval: `.phase5_retrieval` as derived/rebuildable state
- integrated read workspace: `phase6_tutor_workspace.py`
- explicit action boundary: `phase6_academic_agent.py`

This is descriptive metadata for the inventory. It does not rewrite runtime
routing.

## Inventory evidence

For each known legacy/compatibility candidate the scanner records:

- repository path;
- Python module identity;
- component kind;
- intended modern replacement;
- static runtime consumers;
- test-only consumers;
- `main.py` `FEATURE_ACTIONS` dynamic-menu consumers;
- file/data literals such as JSON/DB/Markdown/PDF paths;
- syntactic read/write signal counts;
- parse errors;
- conservative status.

The scanner also automatically inventories:

- `personal_learning_assistant/repositories/json/*.py`
- Phase-4 compatibility `*_backend.py` repository surfaces.

## Status policy

Phase 7.1 uses conservative statuses:

### `active_consumer`

A non-test repository file statically imports/references the candidate, or
`main.py` routes to it via `FEATURE_ACTIONS`.

### `compatibility_required`

The component belongs to an explicit compatibility family, such as legacy JSON
repositories, Phase-4 backends, or the Phase-2/V13 Academic Agent compatibility
service.

This status is retained even if static callers are not discovered.

### `observation_required`

No static runtime caller was discovered, but Phase 7.1 does **not** infer that
the file is dead.

Runtime observation is required.

### `retirement_candidate`

Phase 7.1 deliberately never assigns this status solely from static analysis.

A later phase may assign it only after runtime observation, parity, recovery
proof and explicit retirement policy are satisfied.

## Scanner limitations

The scanner intentionally reports limitations in every inventory:

- subprocess use may be invisible;
- reflection/dynamic strings outside known patterns may be invisible;
- external scripts/plugins may be invisible;
- read/write counts are syntax signals, not proof of authority ownership;
- test-only dependency does not prove normal runtime dependency;
- no static dependency does not prove safety to delete.

## Operator use

JSON report:

```powershell
python .\phase7_runtime_inventory.py `
  --project-root . `
  --format json
```

Markdown report:

```powershell
python .\phase7_runtime_inventory.py `
  --project-root . `
  --format markdown
```

Optional explicit output:

```powershell
New-Item -ItemType Directory -Force .\.phase7 | Out-Null

python .\phase7_runtime_inventory.py `
  --project-root . `
  --format json `
  --output .\.phase7\legacy_inventory.json
```

The gate itself writes inventory output only to a temporary directory.

## No destructive action

Phase 7.1 does not:

- delete/move/archive a candidate;
- modify `main.py`;
- disable a compatibility facade;
- alter SQLite;
- add a migration;
- rewrite legacy JSON;
- rebuild retrieval;
- change Obsidian/source files.

The result is evidence for Phase 7.2–7.7, not a deletion list.

## Next boundary

Phase 7.2 should build the Recovery Bundle + Two Verified Backups.

Do not retire legacy components before recovery and observation evidence exists.
