# Phase 7.5.12 — Obsidian Workspace + Search

## Baseline

- Branch: `main`
- Phase 7.5.11 implementation baseline: `1de4c1a1ee23cf1cf0ae37c63c7b3b7695408d59`
- The Phase 7.5.12 implementation plan must be committed separately before this implementation is committed.

## Objective

Make Obsidian a real ANVAYA workspace for connection status, live Markdown browsing, lexical search, and safe note preview.

## Authority boundaries

- Configuration authority remains `data/obsidian_config.json` through the existing `obsidian_integration.py` non-interactive functions.
- Markdown in the configured Obsidian vault remains authoritative note-body content.
- Phase 5.3 registry/link-graph data is not refreshed or mutated by the web workspace.
- Phase 5.4 Notes Studio mutation commands are not exposed here.
- `.phase5_retrieval` is not rebuilt, updated, or used to represent direct vault search.
- SQLite academic authority is unchanged.

## Web operations

GET operations:

- `/obsidian` — safe status + browse + live lexical search.
- `/obsidian/note?path=...` — fingerprint-verified escaped Markdown preview.

POST operations:

- `/obsidian/connect` — connect/change configured vault.
- `/obsidian/enable` — enable the configured vault.
- `/obsidian/disable` — disable the configured vault.

Successful configuration POSTs use HTTP 303 redirects.

## Search semantics

Vault search is direct local lexical search across:

- note title;
- vault-relative path;
- tags;
- Markdown body.

It is deliberately labeled **Live vault search**. It is not semantic search, RAG, or a retrieval-index rebuild.

## Safety

Phase 7.5.12:

- rejects symlink vault roots;
- never follows symlink files/directories;
- rejects absolute paths and path traversal;
- opens only `.md` notes;
- rescans before preview and verifies the scanner SHA-256 before returning note text;
- refuses stale/external edits rather than displaying mixed content;
- escapes Markdown in Jinja and never uses `|safe` for note content;
- maps filesystem/configuration failures to safe browser messages;
- keeps Flask startup lazy and does not scan/read the vault during app creation;
- does not write, rename, move, trash, restore, archive, or delete Markdown;
- does not call `ObsidianVaultRegistryService.apply()`;
- does not expose Notes Studio write commands;
- does not change tutor/action execution.

## Scope ruling

The repository already has a safer Phase 5.4 Notes Studio write protocol with atomic file writes, expected-hash protection, lifecycle metadata, and operation-journal coordination. Phase 7.5.12 intentionally does not create another Markdown write path. Controlled Obsidian writes will later be exposed through the ANVAYA action layer by reusing Notes Studio.

## Gate

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\phase7_5_fix12_gate.ps1
```

Required final banner:

```text
PHASE 7.5.12 OBSIDIAN WORKSPACE + SEARCH: PASS
```

The gate verifies focused Obsidian tests, Phase 5 scanner/Notes Studio regressions, all Phase 7.5 web regressions, temporary-vault read purity and configuration POST behavior, Phase 7.1–7.4 regressions, the complete pytest suite, Python/dependency/SQLite integrity, protected foundation hashes, dependency direction, exact diff scope, and production SQLite/JSON/retrieval/vault-Markdown reconciliation.

## Deferred

Not included in Phase 7.5.12:

- create/edit/delete Markdown in the web UI;
- Notes Studio lifecycle controls in the web UI;
- registry apply/refresh from the browser;
- backlinks/link-graph UI;
- semantic/FTS vault search;
- retrieval/RAG indexing controls;
- “Ask ANVAYA about this note” source attachment;
- tutor action execution against vault notes.

## Next boundary

Phase 7.5.13 — Tasks + Calendar Operations.
