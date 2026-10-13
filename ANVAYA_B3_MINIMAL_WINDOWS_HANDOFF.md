# Minimal B3 Windows collection

Hosted Ubuntu/Windows CI is development validation. No manual browser screenshots or new test-environment setup is required. This is optional installed-authority collection, not installation/deployment or production migration approval.

Use the existing terminal/environment and Python interpreter you actually use to launch phase7_web.py, from the existing installed ANVAYA repo root on main. The command below fetches the feature objects but pins the immutable tested tools commit ed2bf73, runs its command body and tools outside the installed tree, then removes its private tools. It invokes commands in memory rather than executing a temporary .ps1 file; machine/user execution policy is unchanged. It does not switch your application branch or write academic files. If your launcher uses a different interpreter, replace `(Get-Command python -ErrorAction Stop).Source` with that already-installed interpreter. Do not guess a new environment.

```powershell
& { $ErrorActionPreference='Stop'; $sha='ed2bf73e4b3f1c52d372196da7006889afeb46c9'; git fetch origin anvaya/topic-intelligence-b3-attribution-authority; if ($LASTEXITCODE -ne 0) { throw 'Fetch failed' }; git cat-file -e ($sha+'^{commit}'); if ($LASTEXITCODE -ne 0) { throw 'Pinned tools unavailable' }; $body=(git show ($sha+':scripts/b3_collect_authority.ps1')) -join "`n"; if ($LASTEXITCODE -ne 0) { throw 'Tools unavailable' }; & ([ScriptBlock]::Create($body)) -Python (Get-Command python -ErrorAction Stop).Source -ToolsRef $sha }
```

Default collection does not connect to/copy the DB, so ANVAYA may remain running. It returns installed source/interpreter/launcher hashes, cleanliness, config agreement and backend-control status. It cannot prove actual launcher history or schema/projection parity; production authority remains BLOCKED. Review only the redacted JSON written under your temporary directory.

If you want one report including the genuinely required schema facts, first voluntarily stop ANVAYA **and every app/database/backup/sync writer**, and ensure a safe backup exists. Then run the same single command with `-ClosedNoWriters` added after `-ToolsRef $sha`. This is an explicit attestation, not a process-killing command. Do not add it while any writer may remain active.

The optional phase checks Windows process evidence, rejects invalid controls/unsafe paths/rollback journals, copies the complete main/WAL/SHM set, compares copied/source hashes before SQL access and source stability through inspection, opens only the private copy mode=ro/query_only, checks integrity/FKs/ledger and B3 manifests, and deletes it locally. A failed or uncertain consistency check is BLOCKED. No checkpoint/migration touches the original; no sidecar is deleted from the live tree.

Share **only the redacted JSON**, never a DB/WAL/SHM, vault, learner responses, secrets, private paths or source archive. The source-schema PASS and projection key counts do not certify production authority; absent freshness metadata is UNVERIFIABLE. The reviewer must establish actual launcher/interpreter/checkout and installed ownership/transaction lineage before B3-B.

The source-only helper and default PowerShell path are covered by automated disposable tests and the Windows CI step. Actual-user smoke testing belongs to a later authorized release, not every development iteration.
