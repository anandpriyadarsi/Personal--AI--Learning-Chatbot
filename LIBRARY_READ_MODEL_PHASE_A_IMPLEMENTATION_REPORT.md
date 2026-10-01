# Learning Library Phase A implementation report

Status: IMPLEMENTED, TESTED; WINDOWS VISUAL VALIDATION COMPLETE. Ready for feature-branch publication.

## Repository and scope

Verified remote main on 2026-09-29: `2d05bd06b1f176d06b617ebb626c91eaee10d03b`.
Parent and current HEAD remain that commit. Work is preserved in the isolated
`anvaya/library-read-model-phase-a` checkout. No main merge or modification.
No applicable AGENTS.md was found. Existing backup.py/dashboard.py line-ending
status discrepancies were left untouched and are excluded from Phase A.
Other checkouts were not edited during this continuation.

Added immutable Library contracts, an existing-file read-only SQLite repository,
a presentation service, GET `/library`, GET `/library/resources/<resource_id>`,
list/detail templates, scoped responsive CSS, and one Learning navigation link.
Existing route labels, Resources writes and data authorities remain unchanged.

One active Resource produces one row. Documents with any resource_documents
relationship never appear as ungrouped, including links to hidden Resources.
Details retain all linked Documents; shared Documents remain shared. Canonical
course filtering uses resource_courses, never filenames. Relationships are
batched. SQL applies filters and pagination with updated_at descending,
case-insensitive title, kind and ID ordering. No content-hash deduplication.

Connections require an existing file, URI mode=ro, query_only and a consistent
read transaction. They close reliably, never migrate or change journal mode.
Missing/incompatible storage yields safe 503; unknown/hidden details yield 404;
invalid queries yield 400. Empty and no-match states are distinct. No runtime
source scans, ingestion, embeddings, index access, AI or Moodle calls were added.
Titles are escaped; document paths use display basenames; external links reject
unsafe schemes and credential-bearing URLs. Extraction is not retrieval readiness.

## Configuration and rollback

- LEARNING_LIBRARY_ENABLED defaults to true; false hides the link and returns
  404 before service/database construction.
- LEARNING_LIBRARY_DATABASE_PATH defaults to data/learning_assistant.db.
- LEARNING_LIBRARY_SERVICE_FACTORY supports fixture injection.

Rollback: disable LEARNING_LIBRARY_ENABLED. No data rollback or migration needed.
Native Notes remain JSON/assets, Obsidian remains vault Markdown, Resources 2
and registered Documents remain in their existing SQLite authorities.

## Verification

Fresh execution on 2026-10-01: **109 passed in 4.61s**.
Run from `/workspace/scratch/95c7b6cff813/library-validation`, whose data directory
contains an isolated empty migrated test database needed by the existing /agent
shell smoke test. Production data was not used.

```sh
PYTHONPATH=/workspace/scratch/95c7b6cff813/library-venv/lib/python3.12/site-packages:/workspace/scratch/95c7b6cff813/library-phase-a "$CODEX_PRIMARY_RUNTIME_PYTHON" -m pytest /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_learning_library_read_model.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_learning_library_routes.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_phase5_resources2_core.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_phase7_5_operational_notes_resources.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_phase7_5_anvaya_shell.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_phase7_5_12_2_recovery.py /workspace/scratch/95c7b6cff813/library-phase-a/tests/test_phase7_5_15_10_notes_obsidian_separation.py -q
```

Tests cover grouping, shared/hidden links, canonical filters, deterministic
pagination, immutable models, unavailable schema, no database creation,
row/schema/source/journal read purity, unsafe links, escaping, service injection,
disablement, route behavior and existing regressions. Prior RED/GREEN evidence
is recorded in the execution ledger; this continuation did not recreate the code.
Full project suite was not run: the authorized named regression gate was used.
Tracked Phase A diff whitespace check passed.
Independent whole-diff review found no actionable defects. That reviewer could
not run pytest with default Python; tests above used the configured virtualenv.

## Windows visual validation — PASS

On 2026-10-01 the user explicitly confirmed completing the Windows manual
acceptance checks with no blocking visual or usability defect. Their supplied
instruction confirms mixed material, long/unbroken titles, multiple courses,
Resource detail and multiple Documents, recorded Obsidian-note references,
filters and clearing, no-match, empty and unavailable states, pagination,
desktop, 390px and 320px widths, overflow, keyboard Tab/Shift+Tab and visible
focus, active navigation, readability and contrast.

The final attached screenshots were successfully opened and inspected:
- Screenshot 2026-10-01 131326(1).png: MA103N + Ungrouped documents no-match state.
- Screenshot 2026-10-01 131027(1).png: populated Resource card, wrapped long title,
  two course labels and View resource control.
- Screenshot 2026-10-01 131027(2).png: byte-identical duplicate of the preceding image.

The populated screenshot is cropped at the left edge; it cannot independently
establish viewport overflow. These crops are consistent with the reported
states and do not establish a concrete contradiction to the user's complete
manual results. Mobile, keyboard and interactive acceptance is attributed to
the user's confirmation, not inferred from static desktop screenshots. Earlier
Work-browser access failures are superseded by this Windows acceptance; no
Work-browser visual pass or measured WCAG conformance is claimed.

The temporary fixture self-check was rerun successfully: expected rendered HTML,
write/route isolation, unchanged fixture rows/schema/journal and no missing-DB
creation. The harness's historical PENDING message is not an acceptance record.
No production database, source material or vault was used.

## Final publication checks

- All 13 Phase A files matched the previously reviewed Windows handoff before
  this report-only update. No implementation code was changed on finalization.
- Required seven test files: 109 passed in 4.61s.
- `python -m compileall -q personal_learning_assistant tests`: passed.
- `python -m pip check`: No broken requirements found.
- `git diff --check`: passed; only pre-existing CRLF warnings for the two excluded files.
- Initial index empty. Only the 13 approved files may be staged and committed.
- backup.py and dashboard.py remain byte-for-byte equal to their HEAD versions;
  their existing Git line-ending discrepancies are excluded.
- Local main remains 2d05bd06b1f176d06b617ebb626c91eaee10d03b.
- Remote main was independently verified and fetched as
  b8ce54d02be139c5da62f212e682679368fb656a. That existing Assessment Runner commit
  touches five unrelated files. Phase A retains its approved original parent;
  no rebase, merge, or main update is performed.
- No production/user data exists under this checkout's data, vault or materials
  directories. Tests ran from the separate fixture workspace. No production/user
  data, sources, vault or indexes were opened or modified during finalization.

## Rulings and limitations

- Preserve baseline line-ending discrepancies; cleanup is outside scope.
- Use isolated initialized fixture storage for existing /agent smoke coverage;
  the cost is documenting that existing test prerequisite.
- Reject offsets above SQLite's signed 64-bit range with 400; the cost is
  rejecting impractically large page numbers rather than returning 500.
- No deferred minor review findings.

No new storage authority, migrations, source versions, Notes search/RAG,
Resources cutover, Moodle adoption or navigation consolidation. No Phase B.
