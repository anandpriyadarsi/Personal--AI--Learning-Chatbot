param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15.14/focus-companion-analysis"
$Baseline = "31dfd3e8a60c3e7db7d65ca589dd21f6f14c162b"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.14 FOCUS + COMPANION + ANALYSIS: BLOCKED"
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

function Hash-Tree { param([string]$Root)
  $out=@{}
  if(Test-Path $Root){
    Get-ChildItem $Root -File -Recurse -Force |
      Where-Object {
        $_.Extension -notin @(".pyc",".pyo") -and
        $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
        $_.Name -notin @("learning_assistant.db-wal","learning_assistant.db-shm")
      } |
      Sort-Object FullName |
      ForEach-Object {$out[$_.FullName]=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
  }
  return $out
}

function Assert-Same { param([hashtable]$Before,[hashtable]$After,[string]$Label)
  if($Before.Count -ne $After.Count){Stop-Gate "$Label file count changed."}
  foreach($p in $Before.Keys){
    if(-not $After.ContainsKey($p)){Stop-Gate "$Label removed file: $p"}
    if($Before[$p] -ne $After[$p]){Stop-Gate "$Label changed file: $p"}
  }
}

if(Test-Path $Python){
  $Py=(Resolve-Path $Python).Path
}else{
  $cmd=Get-Command $Python -ErrorAction SilentlyContinue
  if($null -eq $cmd){Stop-Gate "Python not found."}
  $Py=$cmd.Source
}

$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}
git merge-base --is-ancestor $Baseline HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.13 base is not an ancestor of HEAD."}

$Allowed=@(
  "PHASE7_5_15_14_FOCUS_COMPANION_ANALYSIS_SPEC.md",
  "PHASE7_5_15_14_IMPLEMENTATION_REPORT.md",
  "personal_learning_assistant/services/anvaya_notes_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/static/js/app.js",
  "personal_learning_assistant/ui/web/static/js/anvaya_notes_reader.js",
  "personal_learning_assistant/ui/web/templates/base.html",
  "personal_learning_assistant/ui/web/templates/home.html",
  "personal_learning_assistant/ui/web/templates/analysis.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_reader.html",
  "personal_learning_assistant/ui/web/templates/_anvaya_notes_study_tools.html",
  "tests/test_phase7_5_15_14_focus_companion_analysis.py",
  "phase7_5_15_14_gate.ps1"
)
$changed=@(
  git diff --name-only $Range
  git status --porcelain=v1 -uall | ForEach-Object { if($_.Length -ge 4){$_.Substring(3).Trim().Replace("\","/")} }
)
$unexpected=@($changed | Where-Object {$_ -and $_ -notin $Allowed} | Sort-Object -Unique)
if($unexpected.Count){
  $unexpected | ForEach-Object {Write-Host "Unexpected: $_"}
  Stop-Gate "15.14 diff escaped the approved focus/companion/analysis scope."
}

$DataBefore=Hash-Tree ".\data"
$RetrievalBefore=Hash-Tree ".\.phase5_retrieval"
$TutorBefore=Hash-Tree ".\personal_learning_assistant\tutor"
$MigrationsBefore=Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations"

Run-Step "[1/10] Focused Phase 7.5.15.14 tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_14_focus_companion_analysis.py
}
Run-Step "[2/10] Phase 7.5.15.13 card/media regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_13_card_polish_media_delete.py
}
Run-Step "[3/10] Notes separation + inline media regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_10_notes_obsidian_separation.py tests/test_phase7_5_15_11_inline_note_media.py
}
Run-Step "[4/10] Card gallery regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_12_card_template_gallery.py
}
Run-Step "[5/10] Obsidian Companion regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_obsidian_study_repository.py
}
Run-Step "[6/10] Current Home and web regressions" {
  & $Py -m pytest -q tests/test_phase7_5_home.py tests/test_phase7_5_web.py
}
Run-Step "[7/10] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}
Run-Step "[8/10] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[9/10] Authority and protected-data checks"
Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"

$LiveWal=".\data\learning_assistant.db-wal"
if((Test-Path $LiveWal) -and (Get-Item $LiveWal).Length -ne 0){
  Stop-Gate "Production SQLite WAL contains uncheckpointed bytes after validation."
}

Write-Host ""
Write-Host "[10/10] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.14 FOCUS + COMPANION + ANALYSIS: PASS"
Write-Host "================================================================"
Write-Host "Desktop navigation can collapse for full-width reading."
Write-Host "Notes Study Tools is a compact draggable drawer with Saved notes and Doubts."
Write-Host "Detailed academic and Notes analysis is hidden from Home and available in a visual Analysis Hub."
Write-Host "Obsidian, Tutor, production data, retrieval state and SQLite migrations remain protected."
