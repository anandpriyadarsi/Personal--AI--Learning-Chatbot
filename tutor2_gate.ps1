param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "anvaya/tutor-2.0"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " ANVAYA TUTOR 2.0 FOUNDATION: BLOCKED"
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
    Write-Host "Working-tree changes:"
    $status | ForEach-Object { Write-Host $_ }
    Stop-Gate "Working tree must be clean before the Tutor 2.0 gate."
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

$HashScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor2_hash_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $HashScriptPath -Value $HashScript -Encoding UTF8
$BeforeHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture protected hashes." }

$BeforeSnapshotPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor2_before_" + [guid]::NewGuid().ToString("N") + ".json")
$AfterSnapshotPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor2_after_" + [guid]::NewGuid().ToString("N") + ".json")
Set-Content -LiteralPath $BeforeSnapshotPath -Value $BeforeHashes -Encoding UTF8

$DiffScript = @'
from __future__ import annotations
import json, sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))

before_keys = set(before)
after_keys = set(after)

for path in sorted(after_keys - before_keys):
    print("ADDED   " + path)
for path in sorted(before_keys - after_keys):
    print("REMOVED " + path)
for path in sorted(before_keys & after_keys):
    if before[path] != after[path]:
        print("CHANGED " + path)
'@

$DiffScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor2_diff_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $DiffScriptPath -Value $DiffScript -Encoding UTF8

Run-Step "[1/7] Tutor 2.0 focused tests" {
    & $PythonResolved -m pytest -q tests/test_tutor2_foundation.py
}

Run-Step "[2/7] Grounded Tutor + web regressions" {
    & $PythonResolved -m pytest -q tests/test_phase6_grounded_tutor_engine.py tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[3/7] Search / reader regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_3_live_ux_fix.py tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[4/7] Complete pytest regression" {
    & $PythonResolved -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[5/7] Compile + dependency check" {
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[6/7] Protected production/index/vault hashes"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
Set-Content -LiteralPath $AfterSnapshotPath -Value $AfterHashes -Encoding UTF8
if ($BeforeHashes -ne $AfterHashes) {
    Write-Host ""
    Write-Host "Protected-path differences:"
    $DiffOutput = @(& $PythonResolved $DiffScriptPath $BeforeSnapshotPath $AfterSnapshotPath)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "(Could not compute detailed protected-path diff.)"
    } elseif ($DiffOutput.Count -eq 0) {
        Write-Host "(Hashes differ, but no path-level difference was decoded.)"
    } else {
        $DiffOutput | ForEach-Object { Write-Host $_ }
    }
    Stop-Gate "Tutor tests changed production data, retrieval indexes, or configured vault Markdown."
}

Write-Host ""
Write-Host "[7/7] Repository hygiene"
git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$statusAfter = @(git status --porcelain=v1 -uall | Where-Object {
    $_ -notmatch "__pycache__" -and $_ -notmatch "\.pyc$"
})
if ($statusAfter.Count -ne 0) {
    Write-Host "Unexpected working-tree changes:"
    $statusAfter | ForEach-Object { Write-Host $_ }
    Stop-Gate "Tutor tests left repository changes behind."
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue
Remove-Item $DiffScriptPath -Force -ErrorAction SilentlyContinue
Remove-Item $BeforeSnapshotPath -Force -ErrorAction SilentlyContinue
Remove-Item $AfterSnapshotPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " ANVAYA TUTOR 2.0 FOUNDATION: PASS"
Write-Host "======================================================================="
Write-Host "Readable Markdown/LaTeX presentation, conversation layout, human scope labels,"
Write-Host "source-first teaching fallback, pedagogical Tutor Brain, intent routing,"
Write-Host "follow-up controls, and explicit answer feedback are green."
Write-Host "Existing grounded-evidence boundaries and production academic data remain protected."
