param(
  [string]$Python = ".\.venv\Scripts\python.exe",
  [string]$ExpectedBranch = "phase7.5.assessment-studio-d/evaluation-engine"
)
$ErrorActionPreference = "Stop"
$Baseline = "50cfe500dbed6393987a61384f5fa43795c8655e"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " ASSESSMENT STUDIO PHASE D: BLOCKED"
  Write-Host "================================================================"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase C baseline is not an ancestor of HEAD."}

$Allowed=@(
  "ASSESSMENT_STUDIO_PHASE_D.md",
  "ASSESSMENT_STUDIO_PHASE_D_IMPLEMENTATION_REPORT.md",
  "personal_learning_assistant/repositories/sqlite/migrations/0012_assessment_evaluation_engine.sql",
  "personal_learning_assistant/repositories/sqlite/assessment_evaluation_repository.py",
  "personal_learning_assistant/services/assessment_evaluation_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/assessment_test_summary.html",
  "personal_learning_assistant/ui/web/templates/assessment_evaluation_results.html",
  "personal_learning_assistant/ui/web/templates/assessment_evaluation_review.html",
  "tests/test_assessment_studio_phase_a.py",
  "tests/test_assessment_studio_phase_b.py",
  "tests/test_assessment_studio_phase_c.py",
  "tests/test_assessment_studio_phase_d.py",
  "tests/test_phase7_5_12_2_recovery.py",
  "phase7_5_assessment_studio_d_gate.ps1"
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
  Stop-Gate "Phase D diff escaped approved scope."
}

Run-Step "[1/8] Assessment Studio Phase D focused tests" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_d.py
}
Run-Step "[2/8] Assessment Studio Phase A/B/C regressions" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_a.py tests/test_assessment_studio_phase_b.py tests/test_assessment_studio_phase_c.py tests/test_phase7_5_assessments.py
}
Run-Step "[3/8] SQLite schema + recovery regressions" {
  & $Py -m pytest -q tests/test_phase3_sqlite_foundation.py tests/test_phase3_academic_schema.py tests/test_phase7_5_12_2_recovery.py
}
Run-Step "[4/8] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}
Run-Step "[5/8] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}
Run-Step "[6/8] Migration 0001..0012 integrity/FK" {
  & $Py -c "import sqlite3,tempfile; from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; d=Path(tempfile.mkdtemp()); p=d/'a.db'; assert apply_migrations(p)==tuple(range(1,13)); c=sqlite3.connect(p); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
}
Run-Step "[7/8] Evaluation boundary source guard" {
  & $Py -c "from pathlib import Path; s=Path('personal_learning_assistant/services/assessment_evaluation_service.py').read_text(encoding='utf-8'); assert 'topic_progress_events' not in s; assert 'study_plan_items' not in s; assert 'mark_mastered' not in s"
}
Write-Host ""
Write-Host "[8/8] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}
git diff --check
if($LASTEXITCODE -ne 0){Stop-Gate "Working tree diff --check failed."}
git diff --cached --check
if($LASTEXITCODE -ne 0){Stop-Gate "Staged diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " ASSESSMENT STUDIO PHASE D: PASS"
Write-Host "================================================================"
