# Phase 5.2 — Document Registry + Source Scanner

## Starting point

Phase 5.2 starts from the completed Phase 5.1 branch checkpoint:

`f0d65b187670d526ddeaf515652f270de58247d1`

Branch:

`phase5/knowledge-notes-resources`

Phase 4 SQLite authority remains in force. Phase 5.2 must not change the
Phase-4 authority-control state or rewrite legacy structured JSON.

## Objective

Add a deterministic **read-only source scanner** and explicit registration
orchestration on top of the Phase 5.1 knowledge registry.

The scanner may read bytes to calculate SHA-256. It must never move, rename,
rewrite or delete source files.

## Root identity and portable path keys

Every scan uses an explicit logical root key and directory, for example:

`project-documents=C:\...\knowledge\documents`

A source gets a portable path key such as:

`project-documents/linear-algebra/lecture-01.pdf`

Absolute machine paths are not stored as source identity. They exist only in
the in-memory scan fingerprint so the scanner can read the current file.

A different source root key means a different identity namespace.

## Supported registration types

Phase 5.2 can register metadata for:

- Markdown
- plain text
- PDF
- PPT/PPTX
- DOC/DOCX
- JSON/JSONL
- SRT/VTT transcripts
- CSV
- HTML

This does **not** mean Phase 5.2 extracts those formats. Extraction adapters are
Phase 5.6 work.

Unsupported files are counted and ignored rather than guessed.

## Scan safety

The scanner:

- rejects a symlink root;
- never follows symlink directories/files;
- walks deterministically;
- hashes raw bytes in streaming chunks;
- stats a file before and after hashing;
- flags a file that changes during fingerprinting;
- records unreadable sources as explicit issues;
- blocks registration by default when unresolved scan issues exist.

## Stable identity and revisions

Phase 5.1 stable IDs are reused. A source's path key identifies the document;
its SHA-256 identifies the current revision.

Therefore:

- same path + same hash -> `matched`;
- same path + changed hash -> same document ID, `updated`, extraction becomes pending;
- new path -> new document ID.

The scanner does not infer file renames automatically.

## Duplicate candidates

Two registry documents may legitimately contain identical bytes. Phase 5.2
therefore **does not auto-merge by content hash**.

Same-hash documents are returned as duplicate-candidate groups for later human
or domain-specific review.

## Missing/stale registry rows

If a previously registered path under the scanned root is absent from the
current filesystem scan, Phase 5.2 reports its document ID as missing from the
scan. It does not delete or archive the registry row automatically.

## Preview versus apply

`phase5_scan_sources.py` defaults to preview and opens SQLite using `mode=ro`.
It reports aggregate counts only; private filenames are not printed.

Real registration requires both:

`--apply`

and:

`--confirm REGISTER_PHASE5_SOURCES`

The writable database is opened using SQLite `mode=rw`, so a missing production
database can never be silently created.

## Example preview

```powershell
python .\phase5_scan_sources.py `
  --database .\data\learning_assistant.db `
  --root "project-documents=.\knowledge\documents"
```

No real registration should be executed until the Phase 5.2 gate is committed
and a preview has been reviewed.

## Phase boundary

Phase 5.2 intentionally does not scan the configured Obsidian vault as a note
registry. That belongs to **Phase 5.3 — Obsidian Vault Registry + Link Graph**.

It also does not extract source text, create chunks, build FTS, create embeddings
or run RAG.

## Gate

`phase5_fix2_gate.ps1` verifies:

- deterministic fingerprints and portable path keys;
- raw-byte hashes and zero source rewrites;
- symlink safety;
- preview performs zero SQLite writes;
- apply is idempotent on temporary SQLite;
- revisions preserve document identity;
- duplicate candidates are flagged, not merged;
- missing sources are flagged, not deleted;
- real project-documents preview is read-only when the directory exists;
- Phase 5.1 and promoted Phase 4 regressions remain green;
- no migration changes are introduced;
- production SQLite, Phase-4 authority control and legacy JSON hashes remain unchanged.

## Next boundary

Phase 5.3 will establish the Obsidian vault registry, stable note identities,
frontmatter/tag relationships and wiki-link/backlink graph without rewriting
Markdown during its initial scan.
