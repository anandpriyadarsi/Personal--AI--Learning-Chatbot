param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$BaseCommit = "eb53aee70d85d8448d78067e6efa96c3daa33c62"
$ExpectedBranch = "phase4/structured-cutover"
function Stop-Gate { param([string]$Message); Write-Host ""; Write-Host "PHASE 4.4 FIX 4 GATE: BLOCKED"; Write-Host $Message; exit 1 }
function Run-Step { param([string]$Label,[scriptblock]$Command); Write-Host ""; Write-Host $Label; & $Command; if ($LASTEXITCODE -ne 0) { Stop-Gate "$Label failed with exit code $LASTEXITCODE." } }
if (Test-Path $Python) { $PythonResolved=(Resolve-Path $Python).Path } else { $cmd=Get-Command $Python -ErrorAction SilentlyContinue; if ($null -eq $cmd) { Stop-Gate "Python interpreter was not found: $Python" }; $PythonResolved=$cmd.Source }
if ((git branch --show-current).Trim() -ne $ExpectedBranch) { Stop-Gate "Expected branch $ExpectedBranch." }
if ((git rev-parse HEAD).Trim() -ne $BaseCommit) { Stop-Gate "Phase 4.4 must remain uncommitted while gating. Expected HEAD $BaseCommit." }
$allowed=@(
 "personal_learning_assistant/repositories/sqlite/question_topic_mapping_repository.py",
 "personal_learning_assistant/repositories/question_topic_mapping_backend.py",
 "tests/test_phase4_question_topic_mappings_dual_read.py",
 "PHASE4_FIX4_QUESTION_TOPIC_MAPPINGS_DUAL_READ.md",
 "phase4_fix4_gate.ps1"
)
$set=@{}; foreach($p in $allowed){$set[$p]=$true}
foreach($line in @(git status --porcelain=v1 -uall)){ if([string]::IsNullOrWhiteSpace($line)){continue}; $p=$line.Substring(3).Trim().Replace("\","/"); if($p.Contains(" -> ")){$p=$p.Split(" -> ")[-1]}; if(-not $set.ContainsKey($p)){Stop-Gate "Out-of-scope working-tree change detected: $p"} }
foreach($p in @("data/learning_assistant.db","data/learning_assistant.db-wal","data/learning_assistant.db-shm")){ if(Test-Path $p){Stop-Gate "Production SQLite runtime file exists: $p"} }
$phase3=@(Get-ChildItem tests -Filter "test_phase3_*.py" -File | Sort-Object Name | ForEach-Object {$_.FullName}); if($phase3.Count -eq 0){Stop-Gate "No Phase 3 tests found."}
Run-Step "[1/8] Phase 4.4 focused mapping tests" { & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q }
Run-Step "[2/8] Phase 4.3 Questions/Sources regression" { & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q }
Run-Step "[3/8] Phase 4.2 + 4.1 regressions" { & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py tests\test_phase4_courses_dual_read.py -q }
Run-Step "[4/8] All Phase 3 tests" { & $PythonResolved -m pytest $phase3 -q }
Run-Step "[5/8] Full regression suite" { & $PythonResolved -m pytest -q }
Run-Step "[6/8] Python compilation" { & $PythonResolved -m compileall -q . }
Run-Step "[7/8] Dependency consistency" { & $PythonResolved -m pip check }
Write-Host ""; Write-Host "[8/8] Git/repository hygiene"
$staged=@(git diff --cached --name-only); if($staged.Count -ne 0){Stop-Gate "Gate expects no pre-staged changes."}
try { git add --intent-to-add -- $allowed; if($LASTEXITCODE -ne 0){Stop-Gate "git add --intent-to-add failed."}; git diff --check $BaseCommit --; if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."} } finally { git reset --quiet -- $allowed 2>$null }
$private=@(git ls-files -- "data/*.json" "data/**/*.json"); if($private.Count -ne 0){Stop-Gate "Private legacy JSON must remain untracked."}
$runtime=@(git ls-files -- "*.db" "*.db-wal" "*.db-shm"); if($runtime.Count -ne 0){Stop-Gate "SQLite runtime artifacts must not be tracked."}
Write-Host ""; Write-Host "PHASE 4.4 FIX 4 GATE: GREEN"
