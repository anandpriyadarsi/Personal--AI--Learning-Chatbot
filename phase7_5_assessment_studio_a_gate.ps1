param(
  [string]$Python = ".\.venv\Scripts\python.exe",
  [string]$ExpectedBranch = "phase7.5.assessment-studio-a/foundation"
)
$ErrorActionPreference = "Stop"
$Baseline = "05c851a3f5219c2fe80b235f688b6c0d80053a2f"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " ASSESSMENT STUDIO PHASE A: BLOCKED"
  Write-Host "================================================================"
  Write-Host $Message
  exit 1
}

function Run-Step { param([string]$Label,[scriptblock]$Command)
  Write-Host ""
  Write-Host $Label
  & $Command
  if($LASTEXITCODE -ne 0){ Stop-Gate "$Label failed with exit code $LASTEXITCODE." }
}

if(Test-Path $Python){ $Py=(Resolve-Path $Python).Path }
else {
  $cmd=Get-Command $Python -ErrorAction SilentlyContinue
  if($null -eq $cmd){Stop-Gate "Python not found."}
  $Py=$cmd.Source
}

$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}
git merge-base --is-ancestor $Baseline HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "Approved baseline is not an ancestor of HEAD."}

$Allowed=@(
  "ASSESSMENT_STUDIO_PHASE_A.md",
  "personal_learning_assistant/repositories/sqlite/migrations/0009_assessment_studio_foundation.sql",
  "personal_learning_assistant/repositories/sqlite/assessment_studio_repository.py",
  "personal_learning_assistant/services/assessment_studio_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/templates/assessments.html",
  "personal_learning_assistant/ui/web/templates/assessment_templates.html",
  "personal_learning_assistant/ui/web/templates/assessment_course.html",
  "personal_learning_assistant/ui/web/templates/assessment_template_detail.html",
  "personal_learning_assistant/ui/web/templates/assessment_template_form.html",
  "tests/test_assessment_studio_phase_a.py",
  "tests/test_phase7_5_12_2_recovery.py",
  "phase7_5_assessment_studio_a_gate.ps1"
)
$changed=@(
  git diff --name-only $Range
  git status --porcelain=v1 -uall | ForEach-Object {
    if($_.Length -ge 4){$_.Substring(3).Trim().Replace("\","/")}
  }
)
$unexpected=@($changed | Where-Object {$_ -and $_ -notin $Allowed} | Sort-Object -Unique)
if($unexpected.Count){
  $unexpected | ForEach-Object {Write-Host "Unexpected: $_"}
  Stop-Gate "Phase A diff escaped approved scope."
}

Run-Step "[1/7] Assessment Studio Phase A focused tests" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_a.py
}
Run-Step "[2/7] Existing assessment regressions" {
  & $Py -m pytest -q tests/test_phase7_5_assessments.py
}
Run-Step "[3/7] SQLite foundation/schema regressions" {
  & $Py -m pytest -q tests/test_phase3_sqlite_foundation.py tests/test_phase3_academic_schema.py
}
Run-Step "[4/7] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}
Run-Step "[5/7] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}
Run-Step "[6/7] SQLite migration integrity/FK smoke test" {
  & $Py -c "import sqlite3,tempfile; from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; d=Path(tempfile.mkdtemp()); p=d/'a.db'; assert apply_migrations(p)==tuple(range(1,10)); c=sqlite3.connect(p); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
}
Write-Host ""
Write-Host "[7/7] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}
git diff --check
if($LASTEXITCODE -ne 0){Stop-Gate "Working tree diff --check failed."}
git diff --cached --check
if($LASTEXITCODE -ne 0){Stop-Gate "Staged diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " ASSESSMENT STUDIO PHASE A: PASS"
Write-Host "================================================================"
