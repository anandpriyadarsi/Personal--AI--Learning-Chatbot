param(
  [string]$Python = ".\.venv\Scripts\python.exe",
  [string]$ExpectedBranch = "phase7.5.assessment-studio-ux/simplified-authoring"
)
$ErrorActionPreference = "Stop"
$Baseline = "3b87d23ddbe7fac78a76badb9ad6480287a084bb"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "=============================================================="
  Write-Host " ASSESSMENT STUDIO SIMPLIFIED AUTHORING: BLOCKED"
  Write-Host "=============================================================="
  Write-Host $Message
  exit 1
}
function Run-Step { param([string]$Label,[scriptblock]$Command)
  Write-Host ""
  Write-Host $Label
  & $Command
  if($LASTEXITCODE -ne 0){Stop-Gate "$Label failed with exit code $LASTEXITCODE."}
}

if(Test-Path $Python){$Py=(Resolve-Path $Python).Path}else{
  $cmd=Get-Command $Python -ErrorAction SilentlyContinue
  if($null -eq $cmd){Stop-Gate "Python not found."}
  $Py=$cmd.Source
}

$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}
git merge-base --is-ancestor $Baseline HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "Revision-upload baseline is not an ancestor of HEAD."}

Run-Step "[1/7] Simplified authoring tests" {
  & $Py -m pytest -q tests/test_assessment_studio_simplified_authoring.py
}
Run-Step "[2/7] Authoring + blind review tests" {
  & $Py -m pytest -q tests/test_assessment_studio_authoring_ux.py tests/test_assessment_studio_blind_review.py
}
Run-Step "[3/7] Phase B + Assessment Studio A-F regressions" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_b.py tests/test_assessment_studio_phase_a.py tests/test_assessment_studio_phase_c.py tests/test_assessment_studio_phase_d.py tests/test_assessment_studio_phase_e.py tests/test_assessment_studio_phase_f.py tests/test_phase7_5_assessments.py
}
Run-Step "[4/7] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}
Run-Step "[5/7] Compile + dependencies" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}
Run-Step "[6/7] Migration integrity" {
  & $Py -c "import sqlite3,tempfile; from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; d=Path(tempfile.mkdtemp()); p=d/'a.db'; assert apply_migrations(p)==tuple(range(1,15)); c=sqlite3.connect(p); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
}
Write-Host ""
Write-Host "[7/7] Diff hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "=============================================================="
Write-Host " ASSESSMENT STUDIO SIMPLIFIED AUTHORING: PASS"
Write-Host "=============================================================="
