# Minimal Windows handoff

This is a disposable preview, not a release. No live academic database is required. Hosted Windows status is recorded separately in ACCEPTANCE.md; Linux results never certify Windows.

## Optional preview

From an existing ANVAYA clone in PowerShell:

```powershell
git fetch origin
git worktree add ..\anvaya-assessment-preview origin/feature/assessment-pause-paper-2026-10-15
Set-Location ..\anvaya-assessment-preview
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe scripts/assessment_execution_fixture.py --port 8766
```

Open either exact URL printed by the launcher, beginning `http://127.0.0.1:8766/assessments/candidate/sessions/`. The two generated IDs are synthetic; do not substitute a production attempt ID. For restart, use the exact `--resume` command printed by the launcher. Pause first; closing an active tab does not pause time. Do not point normal ANVAYA at the synthetic store.

## The only unresolved local authority evidence

Set `$LivePython` to the interpreter used by your actual installed ANVAYA launcher and `$Repo` to its actual checkout. From that checkout:

```powershell
& $LivePython .\scripts\architecture_local_collector.py --repo $Repo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Default proves only redacted launcher/source/control identity. It does not open a database and does not prove installed schema lineage. Only after ANVAYA, backup and sync writers are shut down, the existing collector's `--closed-no-writers` mode can inspect a stable local copy under its attestation checks. Review schema ledger, collision history, backend/projection identity and parity locally. The collector alone does not grant production authority or reviewed B provenance. Never upload a personal DB, vault, credentials or source bodies.

No repeated manual responsive/browser regression or screenshot session is required. Genuine installed authority remains a real release prerequisite, followed by a brief approved real-user smoke test after an authorized integration.
