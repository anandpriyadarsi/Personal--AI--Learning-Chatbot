# Phase 1.5 portable offline verification

From the repository root, using an already prepared environment:

```sh
python -m scripts.multimodal_validate --full-offline --output verification/phase15-offline.json --suite-timeout 600
```

This single command runs four separately recorded required gates: focused multimodal units, installed real Playwright Chromium journeys, synthetic activation/restore, and integrity. New `tests/test_multimodal_*.py` files are discovered automatically; browser and restore are separate gates. Restore and integrity use disjoint selections in `test_multimodal_restore.py`. Unit tests of the validator never recursively launch its complete suite. All owners and app state come from temporary synthetic fixtures. Screenshots are retained beside the report in `<report-stem>-artifacts/screenshots/`, with absolute paths in the JSON. Each executed gate retains a JUnit XML file and redacted log in the same artifacts directory. The orchestrator does not install dependencies or browsers.

Install the repository's pinned requirements and the approved Playwright/browser version explicitly before validation. A missing Playwright/Chromium executable produces `BLOCKED_ENVIRONMENT`, never PASS. An installed browser that cannot launch or a failing assertion produces FAIL with JUnit/log evidence. `--suite-timeout` bounds each suite; on expiration the complete subprocess tree is terminated. Process groups are cleaned up after normal suite exit too. Browser and synthetic Flask fixtures also close their own resources. Temporary owner roots are removed after the suites; evidence files remain local.

Offline child environments remove credential variables and zero inherited budget/cost settings. An inherited `sitecustomize` guard denies non-loopback DNS and socket connects in Python, including Python children. Chromium runs through a dead local proxy with a localhost-only bypass, so direct external IPs cannot bypass the restriction. Loopback Flask browser journeys remain available. Tests use fake local providers only. No live paid model evaluation or personal activation occurs. Integrity coverage verifies the guard with actual denied external destinations and a successful loopback connection; no external packet needs to be sent to run the probe.

The v2 JSON records actual `platform.system()`, Python/runtime, installed dependency versions, Git SHA and dirty flag. JUnit case elements determine passed/failed/errors/skipped counts; zero tests, errors, skips, timeouts, missing JUnit or nonzero return codes fail a requested gate. Statuses distinguish PASS, FAIL, BLOCKED_ENVIRONMENT and NOT_AUTHORIZED. Every gate records requested/executed flags. `passed` concerns the suites actually selected; `offline_passed` requires all four gates. Unit-only runs cannot claim offline completeness or Windows readiness. Caller-supplied platform descriptions cannot produce a Windows pass: `windows_runtime_verified` requires the actual Windows host and all four gates. `windows_verified` is a compatibility alias for that stricter value. `live_model_quality` remains `unverified`; release readiness remains `conditional` at best until separately authorized release/model/platform requirements are satisfied. A Linux PASS never closes the Windows gate.

For an explicitly prepared Windows environment:

```powershell
.\scripts\multimodal_validate.ps1 -Python .\.venv\Scripts\python.exe -SuiteTimeout 600
```

The wrapper detects existing Python when `-Python` is omitted, runs the same full offline command and packages only redacted JSON/JUnit/logs plus synthetic screenshots into `verification/phase15-windows/phase15-redacted-evidence.zip`. It does not install dependencies, dispatch CI, change billing, or activate stores. If Python is absent or cannot execute, it still writes an explicitly blocked report. Redacted bundle paths are placeholders; the original local JSON keeps usable local evidence paths. No Windows execution is claimed merely because the wrapper exists. Windows must actually run the pinned revision/environment. An unavailable Windows runner remains a pending release gate.

## Synthetic backup/restore contract

Migration preview opens existing SQLite owners with URI `mode=ro&immutable=1` and never creates missing owners. SQLite `mode=ro` alone can create WAL/SHM sidecars. Immutable reads prevent that mutation, but ignore WAL, so preview explicitly refuses nonempty WAL instead of inspecting a stale view. Stop all writers and checkpoint owners through their normal owner before preview; preview never checkpoints them itself. Tests preserve every byte, table and row across preview and reject missing owners.

The restore gate creates stopped synthetic academic and native owners using existing migration/Library fixtures, retains original PNG bytes and notes/config, applies the unchanged optional migration, verifies every backup checksum and SQLite integrity, then restores into a second independent temporary root. Academic and native rows, original SHA-256, notes and config are compared. It exercises idempotent activation and an injected second-owner failure after native activation; both owners must roll back and activation must be retryable. An external vault is deliberately outside the automatic backup claim and remains untouched. The integrity gate pins the historical SQL and combined checksum. No historical migration SQL or checksum is edited.

Personal data is outside this command. If separately authorized later, identify actual owners, stop writers, back up all authoritative originals/notes/assets/config and external owners through their own mechanisms, verify a restore into a different root, then use the existing explicit migration preview/apply. Feature-off rollback is stop app → set `ANVAYA_MULTIMODAL_ENABLED=false` → restart the verified build. It preserves tables, originals, reservations and history; never downgrade or overwrite newer study records.
