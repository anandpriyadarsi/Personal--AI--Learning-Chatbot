# Data integrity, backup, migration and rollback

The implementation uses the existing NativeDocumentLibrary, canonical academic database, Studio store and Assessment engine. Original bytes, native IDs, canonical source IDs, authored revisions and display-title overrides retain separate ownership. There is no title-based merge and no data reset.

## Before updating a real installation

Save or pause active work. Use **Library settings → Export verified backup** and retain the unencrypted export privately outside the checkout. Keep any legacy externally configured source roots separately: files outside `data/` are not implicitly included in a whole-data export. Work has not accessed the user's installed phone databases.

The shared Python backup engine streams ZIP payloads, takes consistent SQLite snapshots, includes hashes/schema metadata, verifies the output and declares pre-existing missing/corrupt originals as recovery tombstones. It does not claim to have backed up missing bytes. The current bounds are 4 GiB expanded, 512 MiB per backup member, 20,000 members; these exceed the original 100 MiB aggregate limit. These are bounded policies, not an unlimited collection guarantee.

Native schema 1→2 remains additive and backup-first. Existing native ID/hash sets, opt-outs and legacy canonical identities are covered by migration fixtures. Existing `documents/<hash>.pdf` registrations keep their original path and canonical ID, with explicit native links. Ambiguous records remain Unsorted. GET browsing never initiates migration. Normal `phase7_web.py` startup is the explicit migration owner.

New authoring drafts and reviewed Assessment identity links are additive feature-owned tables in `learning_studio.sqlite3`; immutable authored content remains in existing modules/assets/publications. Final V3 module snapshots include every original as an owned asset with its exact hash and locator manifest. The derived PDF companion is never called an original Office preview.

Cross-store operations do not claim a multi-database atomic transaction. Native processing jobs/source-links are durable idempotent checkpoints. Course scope links are once-pinned namespaced routed→canonical identities, verified against the current canonical owner at retrieval time; a reused course code cannot retarget historical source evidence. Authoring pins native sources before committing a draft; an interruption can conservatively retain a pin, rather than orphan a lesson. The authoring journal records the operation. Explicit reviewed Assessment topic links do not modify canonical scores/topics.

## Restore

1. Save/pause work; open Library settings and choose the complete export.
2. **Validate and stage restore** rejects traversal, symlinks, duplicate members, unsupported owner schemas, damaged payloads, mismatched hashes and missing promised bytes before changing live data. V1 and V2 archives are accepted. Declared unavailable originals retain metadata and repair records.
3. Stop the server with Ctrl+C. Start `python phase7_web.py` again. Pending restore is applied before owners/workers are opened.
4. The previous directory is retained as `data-before-restore-*`; an interrupted swap has a durable journal and recovery path. Verify original hashes, course/source relations, lesson revisions, attempts and resume before deleting any recovery copy.

Never manually swap a data directory while the server or another owner is running. Never delete the only retained original to force migration success. A failed validation leaves current records active. A failed/cancelled source job cannot publish a superseded generation. Trashing/disabling a source immediately excludes it from live retrieval; when the final active source disappears, the worker publishes a valid empty lexical generation.

## Rollback

Stop the server first and retain both the current data and pre-update verified archive. An older application that cannot understand native schema 2 must not be allowed to write it. Restore the matching pre-upgrade backup into a separate stopped installation and verify it there before choosing it as the active installation. Do not merely check out old code over newer data. Keep source directories and private configuration with their matching installation.

User folders, notes, originals, snapshots, authored revisions and canonical assessments are irreplaceable data. Retrieval generations, native extracted pages and caches are derived. Cleanup must never treat `data/`, native blobs, legacy original roots or Studio source snapshots as a cache.

## Actual synthetic evidence

`test_library2_backup_streaming.py` executes a >100 MiB round trip, V1 import, missing-original tombstones, missing promised-member rejection, incompatible-schema rejection and interrupted swap recovery. `test_web_library_lifecycle.py` exercises streamed web export, CSRF, staged web restore, original image/inert-code serving, explicit startup and read-only legacy resolution. These are synthetic installations; no claim about unavailable private records is made.
