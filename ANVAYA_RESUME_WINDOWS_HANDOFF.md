# ANVAYA B1 deterministic Windows handoff

Gate A base710b249d passed hosted Ubuntu/Windows run38129594236. For B1 replay, use the exact final tested SHA in the delivered handoff; never merge just to test.

Requires Git, Python3.12 and Node22. From your existing repository, fetch and create a separate empty worktree path:

```powershell
git fetch origin anvaya/topic-intelligence-b1-readonly
# Set $TestedSha to the full SHA recorded in the final handoff.
git worktree add --detach ..\ANVAYA-B1-validation $TestedSha
Set-Location ..\ANVAYA-B1-validation
git branch --show-current
git rev-parse HEAD
python .\scripts\architecture_checkout_eol.py --repo .
git status --porcelain=v1 -uall
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-assessment-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe .\scripts\architecture_validation.py --require-clean --output (Join-Path $env:TEMP ('ANVAYA-B1-' + [guid]::NewGuid().ToString('N')))
```

Detached branch output is intentionally empty; HEAD must match the exact tested SHA and status must be empty. EOL helper refuses substantive/unrelated dirty work. Never reset a dirty personal checkout or copy real data/control/vault into validation. No production app is launched. Hosted acceptance replaces manual regression testing; local replay is optional.

## Remaining production-only evidence

Do not switch or migrate the installed checkout. Identify its real path and launcher Python locally as `$InstalledRepo` and `$LivePython`. Set `$Collector` to the absolute `scripts\architecture_local_collector.py` in the separate validation worktree. One command, default identity only (no DB connection/copy):

```powershell
& $LivePython $Collector --repo $InstalledRepo --output (Join-Path $env:TEMP ('ANVAYA-local-authority-' + [guid]::NewGuid().ToString('N') + '.json'))
```

Only if the app plus backup/sync writers are closed and you can attest no writers, append `--closed-no-writers` for copied-schema checking. Never assert this while the app runs. The Windows process check conservatively blocks other Python processes; do not terminate unrelated work automatically.

Share only the redacted JSON, never DB or vault. The collector deletes its temporary copy. Production still requires launcher identity, exact migration/backend lineage, projection freshness/ID parity and release smoke review. Projection key count alone is insufficient. No main merge or deploy is authorized.
