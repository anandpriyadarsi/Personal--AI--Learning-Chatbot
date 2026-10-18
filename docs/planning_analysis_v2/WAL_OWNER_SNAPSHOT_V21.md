# V2.1 WAL academic overview — authorized publication contract

**Implementation:** `personal_learning_assistant/services/academic_wal_snapshot.py`, `AcademicOverviewService` and the `ACADEMIC_WAL_SNAPSHOT_PROVIDER` Flask config key. This is an **opt-in source-owner integration**, not a claim that production authority has been installed.

## Why ordinary WAL mode=ro is not acceptable here

SQLite WAL readers participate in the wal-index: its `-shm` file is memory-mapped and may be created, changed or removed as an effect of connecting/closing even when SQL is `PRAGMA query_only=ON`. `immutable=1` is invalid for live writers: it assumes a static database and can return stale/mismatched data. Never copy database/WAL/SHM files separately, use `nolock=1`, checkpoint to satisfy UI, turn off WAL, or silently relax the physical byte-invariance contract.

## Safe read boundary

Only a **trusted academic writer owner** may call `AcademicSnapshotFeed.publish(owner_connection)` on an existing source connection, **after commit**, on its owning thread:

1. Verify the database's real identity, source connection identity, no pending transaction, WAL mode and a timezone-aware publication time.
2. Use SQLite's online backup API to copy one transactionally consistent committed view to `:memory:`. Normalize its retained WAL page-header bytes using **in-memory VACUUM only**, validate the memory DB, bound serialized size and atomically publish `AuthorizedAcademicSnapshot` under a lock.
3. A Flask Analysis request is passed only `feed.latest`. The request reads a validated, source-identified, revisioned, non-stale in-memory snapshot through SQLite deserialize and `PRAGMA query_only=ON`. It does **not** open the source through SQLite, touch `-wal`/`-shm`, change journal mode, or run migrations.
4. No owner publisher, failed publication, wrong DB, invalid content, timestamp over the configured 120-second TTL, or future publication => **Unavailable**, never `0%` or a supposedly current grade. DELETE-mode source keeps the previous read-only pathway.

Publishing **is an explicit writer-owner operation**, not a physically non-mutating read. SQLite's online backup may coordinate through the owner's WAL index; do not claim source-file byte invariance for the *publication event*. The strict byte-invariance guarantee here covers the **Analysis GET/read operation after publication**.

## Installed application integration — owner authority required

After the existing academic database writer has committed (not before), in the **same process** that serves ANVAYA:

```python
from personal_learning_assistant.services.academic_wal_snapshot import AcademicSnapshotFeed
from personal_learning_assistant.ui.web import create_app

feed = AcademicSnapshotFeed(INSTALLED_ACADEMIC_DB_PATH)

# Hook to the current, authorized academic writer's post-commit mechanism:
def academic_owner_after_committed_write(existing_writer_connection):
    feed.publish(existing_writer_connection)

# Owner must publish an initial snapshot and refresh after every relevant
# committed write. No new SQLite file connection is opened by the GET handler.
app = create_app({
    "ACADEMIC_WAL_SNAPSHOT_PROVIDER": feed.latest,
    "ACADEMIC_WAL_SNAPSHOT_MAX_AGE": 120,
})
```

`INSTALLED_ACADEMIC_DB_PATH` is the same `config.DATABASE_PATH` used in the application's academic overview. An initial publication is required before the first query. Hook publication to **all authorized academic writer paths** and reconfirm data lifecycle/migration safety; blindly adding a second reader/writer connection during a request defeats this feature's safety purpose. No background thread, remote cache, persisted shadow store, production database change or secret transmission is enabled here.

The snapshot is bounded to 128 MiB and held in process-local memory only. It contains real student records; do not print, log, persist in public CI artifacts, or transfer the bytes externally. The UI may show only published-at, revision and freshness metadata.

## Verification / non-goals

Run `python -m pytest -q tests/test_planning_v21_wal_snapshot.py tests/test_planning_analysis_v2.py` in disposable synthetic databases. The cross-platform V2.1 workflow includes both, the full planner characterization matrix and browser journeys. Tests assert: uncheckpointed committed changes visible, uncommitted changes never published, stale/future/mismatched/malformed feeds rejected, wrong publisher connection rejected, no source byte change on Analysis read, and ordinary missing-provider WAL read still fail-closed.

This does **not** automatically certify the installed database, all legacy Planning/Notes/Learning reads, B3-B ownership review, schema migrations or multi-process writer publication. Do not merge/deploy based on synthetic WAL tests alone. Production requires a separately verified installed owner hook, on-device test across all source readers, and source/WAL/SHM fingerprint checks while excluding legitimate concurrent writer updates from the read-only-diff proof.
