# Implementation addendum: automated development, bounded B1 and Assessment

This supplements the attached implementation plan without rewriting recovered audit evidence. The 11 October master prompt is the current execution authority. Baseline remains f859a3c; old Gates A–J reconcile to current A–G exactly as in the attached audit.

## Current authorised sequence

1. **A1 harness branch**: repair only test dependency/fixture portability; unchanged full pytest, original focused tests, both fixture orders, A–D/P01–P08 reproductions, Node, actual headless browser, migration/checksum/FK/integrity and diff checks. CI uses the same Python CLI on Ubuntu/Windows. Characterization green means reproduction; each desired product defect remains FAIL until its owning repair gate.
2. **A2 development proof**: require actual recorded synthetic Ubuntu/Windows jobs, source SHA and artifacts. A local Linux pass is labelled Linux PASS; pending/unavailable Windows remains NOT RUN/BLOCKED. Provisioning green-reviewed CI on a feature branch is not production sign-off. No `continue-on-error`, skip/deselection or obsolete gate substitution.
3. **B1 source-only foundation branch** after A development acceptance: immutable canonical evidence DTO and explicit existing-DB read-only snapshot adapter, no writes/schema/backfill/consumer changes. Historical mapping and independence remain unknown. Record excluded provenance, retain source IDs/bridges and reject cross-course identity. Do not repair the whole legacy GET system or change reports in this slice.
4. **B snapshot-writer/read-safety remainder** after authentic stable schema/ledger and backend/projection lineage review. Nullable reviewed mapping/independence fields only; no historical trust inference. Live unknowns block only this migration slice.
5. **Assessment AP1/AP2**: server-authoritative practice Pause and interrupted/restarted browser tests in a separate branch, after verified execution schema lineage. Preserve exam policy and scored snapshots. This may precede recovery/Analysis/Planning product changes once its own contracts are accepted.
6. **Assessment PS1/PS2**: explicit paper-subjective workspace and versioned self-evaluation source after B provenance contract and verified lineage. Typed self-report evidence never enters v1 independent recovery. No extra student memory.
7. **C → D → E → F → G** as attached plan: exact pure policy, truthful read-only Analysis, canonical planner date/recurrence/capacity/acceptance/completion repairs, automated end-to-end, then Tutor compatibility handoff. No C/D/E implementation is authorised merely by this addendum. Materials/rich recovery/Alex exchange remain deferred follow-ons.

## Exact reproducible development command

Use a disposable environment with tracked `requirements.txt`, `requirements-dev.txt`, `requirements-assessment-browser.txt` and `python -m playwright install chromium` (Linux dependency installation as needed).

`python scripts/architecture_validation.py --output <new-or-validator-owned-directory-outside-repo>`

PowerShell equivalent: `powershell -NoProfile -File .\scripts\architecture_validation.ps1 -Python <verified-test-python>`.

The CLI creates a fresh tracked-source snapshot, never copies a live data tree/control/vault/.env, records source and snapshot hashes, and keeps each run separately. External Python socket connections are blocked; browser tests use synthetic provider replies. Every command's exit code, full log and pytest XML is retained; no failure is turned into an empty success. Screenshots are supporting artifacts, not the sole UX assertions.

## Minimal local Windows release-only work

One collector command, using the **actual launcher interpreter and installed checkout**:

```powershell
& $LivePython .\scripts\architecture_local_collector.py --repo $Repo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

No default DB connection/copy occurs. Only when the app and backup/sync writers are already stopped, add `--closed-no-writers`. It then requires Windows process evidence, copies main/WAL/SHM locally, verifies stable source hashes, opens only the copied DB query-only and deletes that private copy. The shareable JSON contains schema/ledger checks, no records/paths/secrets/vault. Hidden writers remain an operator attestation; do not pretend the process scan proves them absent.

The remaining checklist is three facts: match actual launcher/checkout/interpreter to the redacted source identity; review the closed-copy schema plus backend/projection freshness/ID lineage locally; briefly smoke-test the approved release with the real user. CI replaces repeated manual regression/screenshots, not authentic data authority. Collector output alone never signs off production readiness. No personal database or source body is sent to cloud CI.

## Boundaries and gate meanings

`GATE_A_DEV_AUTOMATED` is current cross-platform synthetic validation. `GATE_A_LOCAL_PRODUCTION_AUTHORITY` retains the old acceptance requirement and stays BLOCKED until real identity/schema/projection evidence is reviewed. Migration filenames cannot be allocated from a fixture alone. Old branch-specific PowerShell gates remain unchanged and incompatible preconditions are reported, never renamed away.

Assessment technical authority: `ANVAYA_ASSESSMENT_PAUSE_OFFLINE_SUBJECTIVE_SPEC.md`. AP0 design is delivered here; AP1/PS persistence is an independently blocked dependency until live lineage is known. User-facing tests, windows/duration policies and evidence trust requirements are fully specified rather than a future wish list.
