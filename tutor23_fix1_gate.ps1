param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "anvaya/tutor-2.3-teaching-orchestration"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " ANVAYA TUTOR 2.3.1 SESSION GOAL + TEACHING PLAN: BLOCKED"
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

function Show-ProtectedHashDiff {
    param(
        [string]$BeforeJson,
        [string]$AfterJson
    )

    $BeforePath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor22_before_" + [guid]::NewGuid().ToString("N") + ".json")
    $AfterPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor22_after_" + [guid]::NewGuid().ToString("N") + ".json")
    Set-Content -LiteralPath $BeforePath -Value $BeforeJson -Encoding UTF8
    Set-Content -LiteralPath $AfterPath -Value $AfterJson -Encoding UTF8

    $DiffScript = @'
from __future__ import annotations
import json, sys
from pathlib import Path

before=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
after=json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))

before_keys=set(before)
after_keys=set(after)
added=sorted(after_keys-before_keys)
removed=sorted(before_keys-after_keys)
modified=sorted(
    key for key in (before_keys & after_keys)
    if before[key] != after[key]
)

if added:
    print("ADDED protected paths:")
    for key in added:
        print("  +", key)
if removed:
    print("REMOVED protected paths:")
    for key in removed:
        print("  -", key)
if modified:
    print("MODIFIED protected paths:")
    for key in modified:
        print("  *", key)
        print("      before:", before[key])
        print("      after: ", after[key])
if not (added or removed or modified):
    print("No protected path-level differences found.")
'@

    $DiffScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("anvaya_tutor22_diff_" + [guid]::NewGuid().ToString("N") + ".py")
    Set-Content -LiteralPath $DiffScriptPath -Value $DiffScript -Encoding UTF8
    & $PythonResolved $DiffScriptPath $BeforePath $AfterPath
    Remove-Item $DiffScriptPath,$BeforePath,$AfterPath -Force -ErrorAction SilentlyContinue
}

function Assert-ProtectedHashesUnchanged {
    param([string]$AfterStep)

    $CurrentHashes = (& $PythonResolved $HashScriptPath).Trim()
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Could not capture protected hashes after $AfterStep."
    }
    if ($BeforeHashes -ne $CurrentHashes) {
        Write-Host ""
        Write-Host "Protected-artifact mutation detected after $AfterStep"
        Show-ProtectedHashDiff -BeforeJson $BeforeHashes -AfterJson $CurrentHashes
        Stop-Gate "Protected production/index/vault state changed during $AfterStep."
    }
}

Run-Step "[1/9] Tutor 2.3.1 session-goal + teaching-plan focused tests" {
    & $PythonResolved -m pytest -q tests/test_tutor23_session_goal_plan.py
}
Assert-ProtectedHashesUnchanged "[1/9] Tutor 2.3.1 focused tests"


Run-Step "[2/9] Tutor 2.2 student-model + signals + memory + personalized-policy regressions" {
    & $PythonResolved -m pytest -q tests/test_tutor22_student_model.py tests/test_tutor22_signal_aggregation.py tests/test_tutor22_memory_candidates.py tests/test_tutor22_personalized_policy.py
}
Assert-ProtectedHashesUnchanged "[2/9] Tutor 2.2 regressions"


Run-Step "[3/9] Tutor 2.1 adaptive + correctness + retrieval + live-fix regressions" {
    & $PythonResolved -m pytest -q tests/test_tutor21_adaptive_intelligence.py tests/test_tutor21_correctness.py tests/test_tutor21_retrieval_planner.py tests/test_tutor21_live_validation_fixes.py
}
Assert-ProtectedHashesUnchanged "[3/9] Tutor 2.1 regressions"


Run-Step "[4/9] Tutor 2.0 foundation + grounded Tutor regressions" {
    & $PythonResolved -m pytest -q tests/test_tutor2_foundation.py tests/test_phase6_tutor_foundation.py tests/test_phase6_grounded_tutor_engine.py tests/test_phase7_5_academic_agent_web.py
}
Assert-ProtectedHashesUnchanged "[4/9] Tutor 2.0/web regressions"


Run-Step "[5/9] Search / reader / retrieval regressions" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_12_3_live_ux_fix.py tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_obsidian_reader_routes.py
}
Assert-ProtectedHashesUnchanged "[5/9] Search/reader/retrieval regressions"


Run-Step "[6/9] Complete pytest regression" {
    & $PythonResolved -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}
Assert-ProtectedHashesUnchanged "[6/9] Complete pytest regression"


Run-Step "[7/9] Compile + dependency check" {
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}
Assert-ProtectedHashesUnchanged "[7/9] Compile/dependency check"


Write-Host ""
Write-Host "[8/9] Protected production/index/vault hashes"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
if ($BeforeHashes -ne $AfterHashes) {
    Show-ProtectedHashDiff -BeforeJson $BeforeHashes -AfterJson $AfterHashes
    Stop-Gate "Tutor 2.3.1 tests changed production data, learning memory, progress, retrieval indexes, or configured vault Markdown."
}

Write-Host ""
Write-Host "[9/9] Repository hygiene"
git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$statusAfter = @(git status --porcelain=v1 -uall | Where-Object {
    $_ -notmatch "__pycache__" -and $_ -notmatch "\.pyc$"
})
if ($statusAfter.Count -ne 0) {
    Write-Host "Unexpected working-tree changes:"
    $statusAfter | ForEach-Object { Write-Host $_ }
    Stop-Gate "Tutor 2.3.1 tests left repository changes behind."
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " ANVAYA TUTOR 2.3.1 SESSION GOAL + TEACHING PLAN: PASS"
Write-Host "======================================================================="
Write-Host "Session-local goal inference/continuity/topic-shift and deterministic teaching plans are green."
Write-Host "Tutor 2.2 memory/personalization, Tutor 2.1 adaptive/correctness/retrieval behavior,"
Write-Host "provider-output hygiene, and Tutor 2.0 safety remain green."
Write-Host "No unapproved production learning-memory, progress, vault, or retrieval-index writes occurred."
