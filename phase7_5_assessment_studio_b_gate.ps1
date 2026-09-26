param(
  [string]$Python = ".\.venv\Scripts\python.exe",
  [string]$ExpectedBranch = "phase7.5.assessment-studio-b/package-import-review"
)
$ErrorActionPreference = "Stop"
$Baseline = "a365ac8377d2354844cbf48170c572e669f85177"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " ASSESSMENT STUDIO PHASE B: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase A baseline is not an ancestor of HEAD."}

$Allowed=@(
  "ASSESSMENT_STUDIO_PHASE_B.md",
  "ASSESSMENT_STUDIO_PHASE_B_IMPLEMENTATION_REPORT.md",
  "ANVAYA_ASSESSMENT_PACKAGE_AUTHORING_PROMPT.md",
  "schemas/anvaya-assessment-package-v1.schema.json",
  "examples/anvaya_assessment_package_v1.example.json",
  "personal_learning_assistant/repositories/sqlite/migrations/0010_assessment_package_import_review.sql",
  "personal_learning_assistant/repositories/sqlite/assessment_import_repository.py",
  "personal_learning_assistant/services/assessment_package_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/templates/assessments.html",
  "personal_learning_assistant/ui/web/templates/assessment_import.html",
  "personal_learning_assistant/ui/web/templates/assessment_import_review.html",
  "personal_learning_assistant/ui/web/templates/assessment_import_question_edit.html",
  "personal_learning_assistant/ui/web/templates/assessment_import_split.html",
  "tests/test_assessment_studio_phase_a.py",
  "tests/test_assessment_studio_phase_b.py",
  "tests/test_phase7_5_12_2_recovery.py",
  "phase7_5_assessment_studio_b_gate.ps1"
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
  Stop-Gate "Phase B diff escaped approved scope."
}

Run-Step "[1/8] Assessment Studio Phase B focused tests" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_b.py
}
Run-Step "[2/8] Phase A assessment foundation regressions" {
  & $Py -m pytest -q tests/test_assessment_studio_phase_a.py tests/test_phase7_5_assessments.py
}
Run-Step "[3/8] SQLite schema + unified recovery regressions" {
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
Run-Step "[6/8] Migration 0001..0010 integrity/FK" {
  & $Py -c "import sqlite3,tempfile; from pathlib import Path; from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations; d=Path(tempfile.mkdtemp()); p=d/'a.db'; assert apply_migrations(p)==tuple(range(1,11)); c=sqlite3.connect(p); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close()"
}
Run-Step "[7/8] Package contract files parse" {
  & $Py -c "import json; from pathlib import Path; json.loads(Path('schemas/anvaya-assessment-package-v1.schema.json').read_text(encoding='utf-8')); json.loads(Path('examples/anvaya_assessment_package_v1.example.json').read_text(encoding='utf-8'))"
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
Write-Host " ASSESSMENT STUDIO PHASE B: PASS"
Write-Host "================================================================"
