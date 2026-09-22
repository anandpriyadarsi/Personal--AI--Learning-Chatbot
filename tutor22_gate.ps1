param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "anvaya/tutor-2.2-student-model"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " ANVAYA TUTOR 2.2 PERSISTENT STUDENT MODEL: BLOCKED"
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
    Stop-Gate "Working tree must be clean before the Tutor 2.2 gate."
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

$HashScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor22_hash_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $HashScriptPath -Value $HashScript -Encoding UTF8
$BeforeHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture protected hashes." }

Run-Step "[1/8] Tutor 2.2 student-model + stable-signal focused tests" {
    & $PythonResolved -m pytest -q tests/test_tutor22_student_model.py tests/test_tutor22_signal_aggregation.py
}

Run-Step "[2/8] Tutor 2.1 adaptive + correctness + retrieval + live-fix regressions" {
    & $PythonResolved -m pytest -q tests/test_tutor21_adaptive_intelligence.py tests/test_tutor21_correctness.py tests/test_tutor21_retrieval_planner.py tests/test_tutor21_live_validation_fixes.py
}

Run-Step "[3/8] Tutor 2.0 foundation + grounded Tutor regressions" {
    & $PythonResolved -m pytest -q tests/test_tutor2_foundation.py tests/test_phase6_tutor_foundation.py tests/test_phase6_grounded_tutor_engine.py tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[4/8] Search / reader / retrieval regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_3_live_ux_fix.py tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[5/8] Complete pytest regression" {
    & $PythonResolved -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[6/8] Compile + dependency check" {
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[7/8] Protected production/index/vault hashes"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
if ($BeforeHashes -ne $AfterHashes) {
    Stop-Gate "Tutor 2.2 tests changed production data, learning memory, progress, retrieval indexes, or configured vault Markdown."
}

Write-Host ""
Write-Host "[8/8] Repository hygiene"
git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$statusAfter = @(git status --porcelain=v1 -uall | Where-Object {
    $_ -notmatch "__pycache__" -and $_ -notmatch "\.pyc$"
})
if ($statusAfter.Count -ne 0) {
    Write-Host "Unexpected working-tree changes:"
    $statusAfter | ForEach-Object { Write-Host $_ }
    Stop-Gate "Tutor 2.2 tests left repository changes behind."
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " ANVAYA TUTOR 2.2 PERSISTENT STUDENT MODEL: PASS"
Write-Host "======================================================================="
Write-Host "Cross-session student context, bounded Tutor signal history/stable aggregation,"
Write-Host "Tutor 2.1 adaptive/correctness/retrieval behavior, topic-shift/follow-up continuity,"
Write-Host "provider-output hygiene, and Tutor 2.0 safety are green."
Write-Host "No global learning-memory, progress, vault, or retrieval-index writes occurred."
