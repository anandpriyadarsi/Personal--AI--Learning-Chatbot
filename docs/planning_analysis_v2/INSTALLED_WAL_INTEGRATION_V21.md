# Normal ANVAYA installation — live WAL academic overview integration

**Entry point:** `python phase7_web.py` on the local Windows installation (also works on Ubuntu). This is code-level integration on the V2.1 feature branch; **not** a claim that the user's actual local database has been accessed or certified.

## Automatic startup contract

1. The existing optional Assessment extension activation and backup safety gates run **first**, unchanged.
2. The launcher validates that `config.DATABASE_PATH` is an existing, ordinary file with a WAL-mode SQLite header. It refuses symlink aliases, absent files and invalid headers without creating a database.
3. For WAL, the launcher starts `InstalledAcademicWalPublisher`: one explicitly owned worker thread opens a **read-only** source connection and publishes a consistent SQLite online-backup to bounded process-local memory. The first publication is attempted before the Flask server starts.
4. The publisher refreshes every **30 seconds** and invalidates its cache on failure. The served overview rejects snapshots older than **120 seconds**, mismatched source identity, corrupt payloads, or future timestamps. If publication cannot be established, Analysis honestly reports *unavailable*, never fabricated zero or a possibly stale live-WAL read.
5. Flask config receives only a callable `ACADEMIC_WAL_SNAPSHOT_PROVIDER=feed.latest` and the canonical `ACADEMIC_DATABASE_PATH`. Planning and Analysis perform in-memory, query-only reads. No source SQLite connection or `-wal/-shm` manipulation occurs in this new academic overview GET path.
6. On normal launcher exit, the publisher is signalled to close its connection. Neither a full checkpoint nor a schema migration is requested by the publisher.

## Source ownership and freshness caveats

The **publication worker** is intentionally authorized to open the live WAL *at startup and periodically*, outside HTTP GET. That process-owned operation may access/create/update SQLite's `-shm` index as an ordinary SQLite participant, and could read an already-active WAL; this is legitimate and is not the same physical-zero-write property as the new academic **GET** read. SQLite's snapshot backup sees committed records; it does not include uncommitted transactions. All screens show the publication timestamp/revision so a 0–30 second lag is visible.

The application has multiple repository owners and both direct sqlite3 connections and the shared `transaction()` helper. No global sqlite3 monkeypatch, migration alteration, injected hidden connections per GET, journal-mode change, writes to academic records, separate persistent copy, remote upload or background **ChatGPT** task are involved. `create_app()`, import of the web app, and unrelated tools remain side-effect free.

Non-WAL databases continue to use the existing read-only overview. The publisher is automatically wired **only in the normal explicit launcher**, not arbitrary Flask imports or WSGI deployments.

**Not yet production approval:** exercise on a *backup or disposable copy* of the installed academic database and review all other legacy `/analysis` page sources (Notes, Learning, Home dashboard) separately. Their SQLite ownership and sidecar mutation behavior has **not** been changed by this feature. The owner-published snapshot feed is safe for the `AcademicOverviewService` component; whole-page filesystem invariance across all other readers and multi-process deployments still require a separate audit.

## Local verification

Run from the feature branch checkout:

```powershell
python -m pytest -q tests/test_planning_v21_wal_snapshot.py tests/test_planning_v21_wal_installed_launcher.py tests/test_planning_analysis_v2.py
python phase7_web.py
```

The process prints only a status such as **connected to committed local snapshots**, or a conservative missing/unavailable state. Open `http://127.0.0.1:5000/analysis` and inspect **Evidence sources & limits** for the committed revision and publication age. The standard local start command has **not** changed.

## Rollout safety

Stacked PR chain: V2.1 reliability #23 → academic WAL #24 → installed local launcher integration (this change). Do not skip parent PRs, merge until CI/owner acceptance, write to production academic records, or include personal SQLite/ZIP course data in public GitHub artifacts.
