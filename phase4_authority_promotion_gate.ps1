param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "eaf49eed699c80cd72a43d4c853682eef27d08db"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 4.9 AUTHORITY PROMOTION GATE: BLOCKED"
    Write-Host "================================================"
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label, [scriptblock]$Command)
    Write-Host ""
    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "$Label failed with exit code $LASTEXITCODE."
    }
}

if (Test-Path $Python) {
    $PythonResolved = (Resolve-Path $Python).Path
}
else {
    $PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $PythonCommand) { Stop-Gate "Python interpreter was not found: $Python" }
    $PythonResolved = $PythonCommand.Source
}

$allowedChanges = @(
    "personal_learning_assistant/migration/authority_promotion.py",
    "tests/test_phase4_authority_promotion.py",
    "PHASE4_9_AUTHORITY_PROMOTION_FOUNDATION.md",
    "phase4_authority_promotion_gate.ps1"
)
foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Required Phase 4.9 file is missing: $path" }
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current Git branch." }
if ($currentBranch -ne $ExpectedBranch) { Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch." }

$currentHead = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current HEAD." }
if ($currentHead -ne $BaseCommit) {
    Stop-Gate "Phase 4.9 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
}

$allowedSet = @{}
foreach ($item in $allowedChanges) { $allowedSet[$item] = $true }
$statusLines = @(git status --porcelain=v1 -uall)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect repository status." }
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim()
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    $path = $path.Replace("\", "/")
    if (-not $allowedSet.ContainsKey($path)) { Stop-Gate "Out-of-scope working-tree change detected: $path" }
}

$protectedPrefixes = @("data/", "knowledge/", "backup/", "NIT KARNATAKA 2026-30/")
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    foreach ($prefix in $protectedPrefixes) {
        if ($path.StartsWith($prefix)) { Stop-Gate "Protected user/source-data path changed: $path" }
    }
}

# Authority promotion starts with safety primitives only. Existing application
# backends and writers must not be changed until writable SQLite command paths
# exist and are separately gated.
$forbiddenFiles = @(
    "config.py",
    "main.py",
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "automatic_topic_mapping.py",
    "assessment_performance.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py",
    "academic_calendar_planner.py",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "personal_learning_assistant/repositories/question_backend.py",
    "personal_learning_assistant/repositories/question_topic_backend.py",
    "personal_learning_assistant/repositories/attempt_performance_backend.py",
    "personal_learning_assistant/repositories/learning_progress_backend.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "personal_learning_assistant/repositories/grade_calendar_backend.py",
    "personal_learning_assistant/repositories/sqlite/course_repository.py",
    "personal_learning_assistant/repositories/sqlite/assessment_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_topic_mapping_repository.py",
    "personal_learning_assistant/repositories/sqlite/attempt_performance_repository.py",
    "personal_learning_assistant/repositories/sqlite/learning_progress_repository.py",
    "personal_learning_assistant/repositories/sqlite/study_plan_repository.py",
    "personal_learning_assistant/repositories/sqlite/grade_calendar_repository.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected application/backends." }
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Phase 4.9 is safety/control foundation only; existing authority paths must remain unchanged."
}

$productionDbPaths = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm"
)
foreach ($path in $productionDbPaths) {
    if (Test-Path $path) { Stop-Gate "Production SQLite runtime file exists before the authority-promotion foundation gate: $path" }
}

$phase4Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase4_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
$phase3Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase3_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($phase4Tests.Count -eq 0) { Stop-Gate "No Phase 4 tests were found." }
if ($phase3Tests.Count -eq 0) { Stop-Gate "No Phase 3 tests were found." }

Run-Step "[1/8] Phase 4.9 authority-promotion focused tests" {
    & $PythonResolved -m pytest tests\test_phase4_authority_promotion.py -q
}
Run-Step "[2/8] Final Phase 4 reconciliation regression" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}
Run-Step "[3/8] All Phase 4 regression tests" {
    & $PythonResolved -m pytest $phase4Tests -q
}
Run-Step "[4/8] All Phase 3 migration/reconciliation/restore tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[5/8] Full project regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[6/8] Python compilation" {
    & $PythonResolved -m compileall -q .
}
Run-Step "[7/8] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[8/8] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.9 gate expects no pre-staged changes."
}
$intentAddFailed = $false
$diffCheckFailed = $false
try {
    git add --intent-to-add -- $allowedChanges
    if ($LASTEXITCODE -ne 0) { $intentAddFailed = $true }
    else {
        git diff --check $BaseCommit --
        if ($LASTEXITCODE -ne 0) { $diffCheckFailed = $true }
    }
}
finally {
    git reset --quiet -- $allowedChanges 2>$null
}
if ($intentAddFailed) { Stop-Gate "Unable to mark Phase 4.9 files intent-to-add for git diff --check." }
if ($diffCheckFailed) { Stop-Gate "git diff --check found whitespace/errors in the Phase 4.9 change set." }

$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked private JSON." }
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host $trackedPrivateJson
    Stop-Gate "Private legacy JSON must remain untracked."
}

$trackedRuntimeArtifacts = @(git ls-files -- "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm" "*.db" "*.db-wal" "*.db-shm")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked SQLite runtime artifacts." }
if ($trackedRuntimeArtifacts.Count -ne 0) {
    Write-Host $trackedRuntimeArtifacts
    Stop-Gate "SQLite runtime databases must remain untracked."
}
foreach ($path in $productionDbPaths) {
    if (Test-Path $path) { Stop-Gate "Gate created or found a production SQLite runtime file: $path" }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 4.9 AUTHORITY PROMOTION GATE: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains eaf49ee and branch is phase4/structured-cutover"
Write-Host "  - current Phase 4.1-4.8 application authority paths are unchanged"
Write-Host "  - local mutation lock is exclusive and ownership-checked"
Write-Host "  - Phase-4 structured inputs can be rehashed without touching Phase-5 domains"
Write-Host "  - SQLite readiness requires migrations 1/2, required tables, integrity_check=ok, and zero FK violations"
Write-Host "  - final structured JSON backup is byte-preserving and SQLite uses online backup API"
Write-Host "  - backup refuses overwrite and refuses the live data directory"
Write-Host "  - backend control supports atomic compare-and-swap replacement"
Write-Host "  - SQLite authority state requires legacy-writer blocking and hash/cutover evidence"
Write-Host "  - legacy-writer guard exists but has not yet been wired into current application writers"
Write-Host "  - no production database/private JSON/Obsidian/knowledge data was created or modified"
Write-Host "  - no authority switch was performed by this foundation"
exit 0
