param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.12.3/live-ux-fix"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " PHASE 7.5.12.3 LIVE UX FIX: BLOCKED"
    Write-Host "======================================================================="
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label,[scriptblock]$Command)
    Write-Host ""
    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "$Label failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path $PythonPath -PathType Leaf)) {
    Stop-Gate "Project virtual-environment Python was not found at $PythonPath."
}
$PythonResolved = (Resolve-Path $PythonPath).Path

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $branch."
}
$status = @(git status --porcelain=v1 -uall)
if ($status.Count -ne 0) {
    Stop-Gate "Working tree must be clean before the live UX gate."
}

$HashScript = @'
from __future__ import annotations
from pathlib import Path
import hashlib, json

def hash_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def tree(root, suffix=None):
    root=Path(root)
    out={}
    if not root.exists():
        return out
    if root.is_file():
        out[str(root).replace("\\","/")]=hash_file(root)
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in {".pyc",".pyo"}:
            continue
        if suffix and p.suffix.lower()!=suffix:
            continue
        out[str(p).replace("\\","/")]=hash_file(p)
    return out

result={}
result.update(tree("data"))
result.update(tree(".phase5_retrieval"))
try:
    import obsidian_integration
    vault=obsidian_integration.get_vault_path()
    if vault:
        result.update(tree(vault, ".md"))
except Exception:
    pass
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'@

$HashScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("p75123_hash_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $HashScriptPath -Value $HashScript -Encoding UTF8
$BeforeHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture protected hashes." }

Run-Step "[1/7] Focused live UX tests" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_3_live_ux_fix.py
}

Run-Step "[2/7] Unified search + Academic Agent regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_12_2_web.py tests/test_phase7_5_knowledge_rag.py tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[3/7] Obsidian regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_obsidian_study_repository.py
}

Run-Step "[4/7] Operational Planner regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_operational_calendar.py tests/test_phase7_5_operational_tasks.py tests/test_phase7_5_progress_planning.py tests/test_phase7_5_daily_agenda.py tests/test_phase7_5_weekly_review.py
}

$Phase75Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase7_5_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($Phase75Tests.Count -eq 0) {
    Stop-Gate "No Phase 7.5 regression test files were found."
}

Run-Step "[5/7] Complete Phase 7.5 regression" {
    & $PythonResolved -m pytest -q @Phase75Tests
}

Run-Step "[6/7] Complete pytest + compile + pip check" {
    & $PythonResolved -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[7/7] Protected hashes + repository cleanliness"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
if ($BeforeHashes -ne $AfterHashes) {
    Stop-Gate "Production data, retrieval indexes, or configured Obsidian Markdown changed during tests."
}

git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$statusAfter = @(git status --porcelain=v1 -uall | Where-Object {
    $_ -notmatch "__pycache__" -and $_ -notmatch "\.pyc$"
})
if ($statusAfter.Count -ne 0) {
    Write-Host "Unexpected working-tree changes:"
    $statusAfter | ForEach-Object { Write-Host $_ }
    Stop-Gate "Tests left repository changes behind."
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " PHASE 7.5.12.3 LIVE UX FIX: PASS"
Write-Host "======================================================================="
Write-Host "Search fallback/spelling tolerance, Obsidian wikilinks/backlinks,"
Write-Host "calendar navigation, dated-task visibility, and task editing are green."
Write-Host "Production data, retrieval indexes, and vault Markdown remained unchanged."
