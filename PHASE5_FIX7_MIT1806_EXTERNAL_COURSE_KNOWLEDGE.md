# Phase 5.7 — MIT 18.06 / External Course Knowledge

## Starting point

Phase 5.7 starts from `50469533a96f2b6e2045884f2b538a29cff0583d`
(`feat: add Phase 5.6 unified ingestion pipeline`) on
`phase5/knowledge-notes-resources`.

## Source-grounded package decision

The supplied MIT 18.06 package contains:

- one `course_manifest.json`;
- one 35-record `lecture_inventory.json`;
- one `schema.json`;
- one 261-record `chunks.jsonl`;
- 175 lecture chunks and 86 concept chunks according to the manifest.

The baseline audit explicitly classifies this package as external-course
knowledge that should be **related to MA103N, not relabelled as MA103N**.

The package itself states that its chunks are original analytical paraphrases
grounded in official MIT OpenCourseWare sources. It is not a corpus of verbatim
MIT transcripts. Phase 5.7 therefore preserves source URLs/scope notes exactly
and does not fabricate transcript files or claim transcript provenance that the
package does not provide.

## No schema migration

Phase 5.7 intentionally reuses the Phase 3 / Phase 5 schema:

- external course = Resources 2 `external_course`;
- each lecture = Resources 2 `external_lecture`;
- relation to NITK course = `resource_courses`;
- exact MA103N topic matches = `resource_topics`;
- package files = `knowledge_documents`;
- package semantic units = `knowledge_chunks`;
- source relationships = `resource_documents`;
- Phase 5.8 handoff = `index_jobs` + `outbox_events`.

This avoids changing historical Phase 3 migration semantics and keeps Phase 3
regression expectations intact.

## Stable identity

Provider is `mit_ocw`.

External IDs are:

- course: `mit-18.06-linear-algebra`
- lecture: `mit-18.06-linear-algebra:lecture:<lecture_number>`

If an exact provider/external ID already exists, Phase 5.7 matches it instead of
creating a duplicate. User-owned resource state such as progress, rating and
quality note is preserved during re-apply.

## Package validation

Before preview/apply, the reader validates:

- package course ID;
- manifest course/instructor/version;
- manifest counts versus actual inventory/chunks;
- unique lecture numbers;
- unique chunk IDs;
- every chunk's `content_hash == SHA256(exact text)`;
- every lecture reference exists in the inventory;
- MIT source provider;
- official `https://ocw.mit.edu/` source/supporting URLs.

The four authoritative package files are hashed exactly.

## MA103N crosswalk

Topic mapping is deliberately conservative.

A package topic/concept label is linked to MA103N only when its normalized text
matches exactly one active MA103N topic name, normalized name or registered
topic alias.

No fuzzy mapping is performed.

Unresolved/ambiguous labels stay present in the authoritative package inventory
and per-chunk provenance and are reported by preview. They are not guessed into
local topic IDs.

## Resources 2 projection

The package creates/plans:

- one external-course resource;
- 35 lecture resources;
- course/lecture links to MA103N without changing course identity;
- exact topic links where proven;
- course metadata/source document links.

Lecture canonical URIs remain the official lecture URLs from
`lecture_inventory.json`.

## Deterministic package ingestion

`chunks.jsonl` is registered as one knowledge document with exact source-file
SHA-256.

Its 261 source-authored answer-sized chunks are not re-split by the generic
Phase 5.6 character chunker. Their existing stable `chunk_id`, exact text hash,
chunk type and source semantics are preserved in a deterministic ingestion
version:

`external-course-package-v1 | package-version | chunks-file-hash-prefix`

The `knowledge_chunks` locator envelope preserves:

- package chunk ID;
- MIT external-course ID;
- lecture number(s)/title;
- topic/concepts/prerequisites/related concepts;
- NITK week labels and priority from the package;
- source provider/kind/title/scope note;
- official source URL;
- supporting official source URLs;
- retrieval-query examples;
- answer modes;
- content version.

The SQLite chunk ID is deterministic from course ID + extraction version +
package chunk ID.

## Retrieval handoff

Successful package apply creates one idempotent pending
`retrieval_handoff` job for the chunks document and one
`knowledge.external_course.ingested` outbox event.

Phase 5.7 does **not** build FTS, embeddings, semantic indexes, hybrid retrieval
or RAG. Phase 5.8 owns that work.

## Operator CLI

Read-only preview using the configured vault:

```powershell
python .\phase5_external_course_knowledge.py `
  --database .\data\learning_assistant.db `
  --configured-vault `
  --local-course MA103N `
  --expect-lectures 35 `
  --expect-chunks 261
```

Real registration/ingestion requires the exact phrase:

```text
--apply --confirm REGISTER_MIT1806_EXTERNAL_COURSE
```

Do not perform the real apply until the Phase 5.7 gate is green and preview
counts have been reviewed.

## Safety

- package files remain authoritative and read-only;
- no network request is made;
- official source provenance is not rewritten;
- MIT chunks are not relabelled as MA103N;
- no fuzzy topic mapping;
- no new migration;
- preview opens production SQLite read-only;
- tests use synthetic package/temporary SQLite only;
- gate hashes production SQLite, Phase 4 authority, legacy JSON and real package
  files before/after.

## Next boundary

Phase 5.8 consumes the pending retrieval handoffs to build disposable,
rebuildable lexical and semantic indexes with provenance-aware filtering and
source-grounded retrieval.


## Crosswalk reconciliation addendum

The first real Phase 5.7 preview showed:

- 82 unique external labels;
- 0 exact MA103N mappings;
- 82 unresolved labels;
- 0 ambiguous exact matches.

That result is preserved as evidence that exact-only mapping was too conservative
for the current local naming vocabulary, not as permission to introduce fuzzy
automatic writes.

Phase 5.7 now includes an explicit reviewed-crosswalk workflow.

### Review artifact

`phase5_mit1806_crosswalk.py` can generate a JSON review template from the real
MIT package and current MA103N topics/aliases. The template contains:

- package/course identity and source-manifest hash;
- current local topic IDs/names/aliases;
- one row for every unique MIT topic/concept label;
- exact-match state;
- review-only similarity suggestions.

Suggestions never map automatically.

For each non-exact label, the reviewer must choose one of:

- `map` + exact current `target_topic_id`/`target_topic_name`;
- `leave_unresolved`;
- `pending`.

`pending` blocks real Phase 5.7 apply.

The reviewed artifact is bound to the exact external course ID, package version,
package source-manifest hash, local course code and local course ID. Package or
course drift therefore invalidates an old crosswalk instead of silently reusing
it.

### Crosswalk provenance

The canonical semantic review decisions produce `crosswalk_sha256`.

That hash is included in:

- the external-package extraction version;
- the Phase 5.8 handoff index version;
- every imported package chunk locator;
- the external-course ingestion outbox payload.

Changing reviewed mappings creates a new extraction/index handoff identity even
when the MIT package bytes are unchanged. Older same-content handoff jobs become
`stale`.

### Topic-aware chunk provenance

Imported chunks preserve three distinct local relationships:

- `local_topic_ids` — mapped package topic/concepts;
- `local_prerequisite_topic_ids` — mapped prerequisites;
- `local_related_topic_ids` — mapped related concepts.

Lecture resources receive mapped topic/concept links for their own lecture
scope. The external-course resource receives the union of mapped topic IDs.
MIT course identity remains unchanged.

### Real apply safety

Real package apply now requires `--crosswalk` and a complete reviewed artifact.
This prevents the previously observed `0/82` topic-crosswalk state from being
silently installed.

Generate the review template first:

```powershell
python .\phase5_mit1806_crosswalk.py `
  --database .\data\learning_assistant.db `
  --configured-vault `
  --local-course MA103N `
  --export-template .\phase5_work\mit1806_ma103n_crosswalk.json
```

Review the JSON, then validate it read-only:

```powershell
python .\phase5_mit1806_crosswalk.py `
  --database .\data\learning_assistant.db `
  --configured-vault `
  --local-course MA103N `
  --crosswalk .\phase5_work\mit1806_ma103n_crosswalk.json
```

Only after every non-exact label is explicitly reviewed should the package apply
be allowed.
