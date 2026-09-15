param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "b76d262b98abacff1a4481ce5b11f499c7f25e8c"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "==============================================="
    Write-Host " PHASE 4.10 SQLITE COMMAND/GUARD GATE: BLOCKED"
    Write-Host "==============================================="
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
    "personal_learning_assistant/repositories/authority_guard.py",
    "personal_learning_assistant/repositories/sqlite/command_repositories.py",
    "personal_learning_assistant/repositories/json/course_repository.py",
    "personal_learning_assistant/repositories/json/assessment_repository.py",
    "personal_learning_assistant/repositories/json/question_repository.py",
    "personal_learning_assistant/repositories/json/learning_progress_repository.py",
    "personal_learning_assistant/repositories/json/study_plan_repository.py",
    "personal_learning_assistant/repositories/json/grade_calendar_repository.py",
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py",
    "tests/test_phase4_sqlite_command_repositories.py",
    "PHASE4_10_SQLITE_COMMAND_REPOSITORIES_LEGACY_GUARDS.md",
    "phase4_fix10_gate.ps1"
)

foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 4.10 file is missing: $path"
    }
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current Git branch." }
if ($currentBranch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch."
}

$currentHead = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current HEAD." }
if ($currentHead -ne $BaseCommit) {
    Stop-Gate "Phase 4.10 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
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
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change detected: $path"
    }
}

# Phase 4.10 may add fail-closed pre-write guards to the old procedural
# structured writers, but it must not route those APIs to SQLite yet.  All
# shadow readers/backends and unrelated public modules remain untouched.
$protectedFiles = @(
    "main.py",
    "config.py",
    "automatic_topic_mapping.py",
    "assessment_performance.py",
    "academic_calendar_planner.py",
    "personal_learning_assistant/migration/authority_promotion.py",
    "personal_learning_assistant/repositories/interfaces.py",
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
$protectedChanges = @(git status --porcelain=v1 -- $protectedFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected Phase 4 files." }
if ($protectedChanges.Count -ne 0) {
    Write-Host $protectedChanges
    Stop-Gate "Phase 4.10 must not modify shadow readers/backends or unrelated public routing."
}

$protectedPrefixes = @("data/", "knowledge/", "backup/", "NIT KARNATAKA 2026-30/")
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    foreach ($prefix in $protectedPrefixes) {
        if ($path.StartsWith($prefix)) {
            Stop-Gate "Protected user/source-data path changed: $path"
        }
    }
}

$forbiddenRuntime = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm",
    ".phase4_authority.json",
    ".phase4_cutover.lock"
)
foreach ($path in $forbiddenRuntime) {
    if (Test-Path $path) { Stop-Gate "Phase 4.10 must not create runtime authority artifact: $path" }
}

# Structural source checks are deliberately cheap/fail-fast before pytest.
$commandSource = Get-Content "personal_learning_assistant/repositories/sqlite/command_repositories.py" -Raw
if ($commandSource -match "learning_assistant\.db" -or $commandSource -match "DATABASE_PATH" -or $commandSource -match "connect_database\(") {
    Stop-Gate "SQLite command repositories contain an implicit production database/open path."
}
if ($commandSource -notmatch "storage_backend" -or $commandSource -notmatch "legacy_writes_blocked") {
    Stop-Gate "SQLite command repositories do not visibly enforce the Phase 4 authority state."
}

$guardedRepos = @(
    "personal_learning_assistant/repositories/json/course_repository.py",
    "personal_learning_assistant/repositories/json/assessment_repository.py",
    "personal_learning_assistant/repositories/json/question_repository.py",
    "personal_learning_assistant/repositories/json/learning_progress_repository.py",
    "personal_learning_assistant/repositories/json/study_plan_repository.py",
    "personal_learning_assistant/repositories/json/grade_calendar_repository.py"
)
foreach ($path in $guardedRepos) {
    $text = Get-Content $path -Raw
    if ($text -notmatch "guard_legacy_structured_write") {
        Stop-Gate "Legacy repository writer is missing Phase 4.10 guard wiring: $path"
    }
}

$guardedProceduralWriters = @(
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py"
)
foreach ($path in $guardedProceduralWriters) {
    $text = Get-Content $path -Raw
    if ($text -notmatch "guard_legacy_structured_write" -or $text -notmatch "infer_authority_control_path") {
        Stop-Gate "Procedural structured writer is missing Phase 4.10 guard wiring: $path"
    }
    if ($text -match "repositories\.sqlite\.command_repositories" -or $text -match "SQLite[A-Za-z]+CommandRepository") {
        Stop-Gate "Phase 4.10 must not route procedural APIs to SQLite command repositories yet: $path"
    }
}

$phase4Tests = @(
    "tests\test_phase4_courses_dual_read.py",
    "tests\test_phase4_assessments_dual_read.py",
    "tests\test_phase4_questions_dual_read.py",
    "tests\test_phase4_question_topic_mappings_dual_read.py",
    "tests\test_phase4_attempts_performance_dual_read.py",
    "tests\test_phase4_learning_progress_dual_read.py",
    "tests\test_phase4_study_plans_dual_read.py",
    "tests\test_phase4_grades_calendar_dual_read.py"
)
foreach ($path in $phase4Tests) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Missing Phase 4 regression: $path" }
}

$phase3Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase3_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($phase3Tests.Count -eq 0) { Stop-Gate "No Phase 3 regression/safety tests were found." }

Run-Step "[1/15] Phase 4.10 writable SQLite command + legacy guard tests" {
    & $PythonResolved -m pytest tests\test_phase4_sqlite_command_repositories.py -q
}
Run-Step "[2/15] Phase 4.9 authority-promotion foundation regression" {
    & $PythonResolved -m pytest tests\test_phase4_authority_promotion.py -q
}
Run-Step "[3/15] Final Phase 4 reconciliation regression" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}
Run-Step "[4/15] Phase 4.8 Grades + Calendar regression" {
    & $PythonResolved -m pytest tests\test_phase4_grades_calendar_dual_read.py -q
}
Run-Step "[5/15] Phase 4.7 Study Plans regression" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[6/15] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[7/15] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[8/15] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[9/15] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[10/15] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[11/15] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[12/15] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[13/15] Full project regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[14/15] Python compilation and installed dependency consistency" {
    & $PythonResolved -m compileall -q .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[15/15] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.10 gate expects no pre-staged changes."
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
if ($intentAddFailed) { Stop-Gate "Unable to mark Phase 4.10 files intent-to-add." }
if ($diffCheckFailed) { Stop-Gate "git diff --check found whitespace/errors." }

$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked private JSON." }
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host $trackedPrivateJson
    Stop-Gate "Private legacy JSON must remain untracked."
}

$trackedRuntimeArtifacts = @(git ls-files -- "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm" ".phase4_authority.json" ".phase4_cutover.lock")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked runtime artifacts." }
if ($trackedRuntimeArtifacts.Count -ne 0) {
    Write-Host $trackedRuntimeArtifacts
    Stop-Gate "Production authority/runtime artifacts must remain untracked."
}
foreach ($path in $forbiddenRuntime) {
    if (Test-Path $path) { Stop-Gate "Gate created or found runtime authority artifact: $path" }
}

Write-Host ""
Write-Host "=============================================="
Write-Host " PHASE 4.10 SQLITE COMMAND/GUARD GATE: PASS"
Write-Host "=============================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains b76d262 on phase4/structured-cutover"
Write-Host "  - SQLite command repositories require explicit connection + SQLite authority control"
Write-Host "  - legacy/dual-read states cannot mutate SQLite through the new command surface"
Write-Host "  - course, assessment, question/performance, learning/progress, plan, grade/calendar commands are transactional"
Write-Host "  - repository and procedural legacy writers are blocked before byte changes after SQLite promotion"
Write-Host "  - procedural guards run before legacy data-directory/temp-file creation"
Write-Host "  - missing/dual-read control preserves legacy writer behavior"
Write-Host "  - authority control is outside data/ and no production DB/control artifact was created"
Write-Host "  - Phase 4.1-4.9, final reconciliation, Phase 3 and full regressions pass"
Write-Host "  - shadow readers/backends remain unchanged; procedural APIs are guarded but not rerouted"
Write-Host "  - production authority has NOT been switched by this phase"
exit 0
