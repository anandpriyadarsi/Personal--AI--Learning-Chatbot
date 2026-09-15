param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "a6786de29dfdaaa1ab10bfb2eae005d069164c08"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================="
    Write-Host " FINAL PHASE 4 STRUCTURED RECONCILIATION GATE: BLOCKED"
    Write-Host "======================================================="
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
    if ($null -eq $PythonCommand) {
        Stop-Gate "Python interpreter was not found: $Python"
    }
    $PythonResolved = $PythonCommand.Source
}

$allowedChanges = @(
    "personal_learning_assistant/repositories/phase4_reconciliation.py",
    "tests/test_phase4_final_reconciliation.py",
    "PHASE4_FINAL_STRUCTURED_CUTOVER_RECONCILIATION.md",
    "phase4_final_gate.ps1"
)

foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required final Phase 4 file is missing: $path"
    }
}

$requiredHistoryFiles = @(
    "PHASE4_FIX1_COURSES_TOPICS_DUAL_READ.md",
    "PHASE4_FIX2_ASSESSMENTS_DUAL_READ.md",
    "PHASE4_FIX3_QUESTIONS_SOURCES_DUAL_READ.md",
    "PHASE4_FIX4_QUESTION_TOPIC_MAPPINGS_DUAL_READ.md",
    "PHASE4_FIX5_ATTEMPTS_MISTAKES_PERFORMANCE_DUAL_READ.md",
    "PHASE4_FIX6_LEARNING_MEMORY_ACADEMIC_PROGRESS_DUAL_READ.md",
    "PHASE4_FIX7_STUDY_PLANS_DUAL_READ.md",
    "PHASE4_FIX8_GRADES_ACADEMIC_CALENDAR_DUAL_READ.md",
    "phase4_fix1_gate.ps1",
    "phase4_fix2_gate.ps1",
    "phase4_fix3_gate.ps1",
    "phase4_fix4_gate.ps1",
    "phase4_fix5_gate.ps1",
    "phase4_fix6_gate.ps1",
    "phase4_fix7_gate.ps1",
    "phase4_fix8_gate.ps1",
    "personal_learning_assistant/migration/reconciliation_reports.py",
    "personal_learning_assistant/migration/reverse_export_restore.py"
)
foreach ($path in $requiredHistoryFiles) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required prior Phase 3/4 evidence is missing: $path"
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
    Stop-Gate "Final Phase 4 gate must remain uncommitted while validating. Expected HEAD $BaseCommit but found $currentHead."
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

$protectedPrefixes = @(
    "data/",
    "knowledge/",
    "backup/",
    "NIT KARNATAKA 2026-30/"
)
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    foreach ($prefix in $protectedPrefixes) {
        if ($path.StartsWith($prefix)) {
            Stop-Gate "Protected user/source-data path changed: $path"
        }
    }
}

# The final reconciliation gate must not rewrite the completed Phase 4 domains or
# public legacy-authoritative application modules merely to make the gate green.
$forbiddenFiles = @(
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
    "academic_intelligence_dashboard.py",
    "daily_academic_brief.py",
    "personal_academic_agent.py",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "personal_learning_assistant/repositories/question_backend.py",
    "personal_learning_assistant/repositories/question_topic_backend.py",
    "personal_learning_assistant/repositories/attempt_performance_backend.py",
    "personal_learning_assistant/repositories/learning_progress_backend.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "personal_learning_assistant/repositories/grade_calendar_backend.py",
    "personal_learning_assistant/migration/courses_topics_importer.py",
    "personal_learning_assistant/migration/assessments_topics_importer.py",
    "personal_learning_assistant/migration/questions_sources_importer.py",
    "personal_learning_assistant/migration/question_topic_mappings_importer.py",
    "personal_learning_assistant/migration/attempts_performance_importer.py",
    "personal_learning_assistant/migration/learning_progress_importer.py",
    "personal_learning_assistant/migration/study_plans_importer.py",
    "personal_learning_assistant/migration/grades_calendar_importer.py",
    "personal_learning_assistant/migration/reconciliation_reports.py",
    "personal_learning_assistant/migration/reverse_export_restore.py",
    "tests/test_phase4_courses_dual_read.py",
    "tests/test_phase4_assessments_dual_read.py",
    "tests/test_phase4_questions_dual_read.py",
    "tests/test_phase4_question_topic_mappings_dual_read.py",
    "tests/test_phase4_attempts_performance_dual_read.py",
    "tests/test_phase4_learning_progress_dual_read.py",
    "tests/test_phase4_study_plans_dual_read.py",
    "tests/test_phase4_grades_calendar_dual_read.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected Phase 4 implementation files." }
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Final reconciliation must not modify completed Phase 4.1-4.8 implementation files."
}

$productionDbPaths = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm"
)
foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate "Production SQLite runtime file exists: $path"
    }
}

$phase3Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase3_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($phase3Tests.Count -eq 0) {
    Stop-Gate "No Phase 3 regression/safety tests were found."
}

Run-Step "[1/15] Final Phase 4 cross-domain reconciliation/readiness tests" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}
Run-Step "[2/15] Phase 4.8 Grades + Academic Calendar regression" {
    & $PythonResolved -m pytest tests\test_phase4_grades_calendar_dual_read.py -q
}
Run-Step "[3/15] Phase 4.7 Study Plans regression" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[4/15] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[5/15] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[6/15] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[7/15] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[8/15] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[9/15] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[10/15] Phase 3 reconciliation + reverse-export/restore safety regression" {
    & $PythonResolved -m pytest tests\test_phase3_reconciliation_reports.py tests\test_phase3_reverse_export_restore.py -q
}
Run-Step "[11/15] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[12/15] Complete project regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[13/15] Python compilation" {
    & $PythonResolved -m compileall -q .
}
Run-Step "[14/15] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[15/15] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Final Phase 4 gate expects no pre-staged changes so new files can be validated safely."
}
$intentAddFailed = $false
$diffCheckFailed = $false
try {
    git add --intent-to-add -- $allowedChanges
    if ($LASTEXITCODE -ne 0) {
        $intentAddFailed = $true
    }
    else {
        git diff --check $BaseCommit --
        if ($LASTEXITCODE -ne 0) { $diffCheckFailed = $true }
    }
}
finally {
    git reset --quiet -- $allowedChanges 2>$null
}
if ($intentAddFailed) {
    Stop-Gate "Unable to mark final Phase 4 files intent-to-add for git diff --check."
}
if ($diffCheckFailed) {
    Stop-Gate "git diff --check found whitespace/errors in the final Phase 4 change set."
}

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
    Stop-Gate "SQLite runtime databases must remain temporary and untracked."
}
foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate "Gate created or found a production SQLite runtime file: $path"
    }
}

Write-Host ""
Write-Host "===================================================="
Write-Host " FINAL PHASE 4 STRUCTURED RECONCILIATION GATE: PASS"
Write-Host "===================================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains a6786de and branch is phase4/structured-cutover"
Write-Host "  - Phase 4.1 through Phase 4.8 focused regressions are green"
Write-Host "  - all eight structured-domain parity families remain explicit"
Write-Host "  - SQLite integrity/foreign-key and migration-ledger target checks are read-only"
Write-Host "  - documented deferred parity is review-required, never silently passed"
Write-Host "  - all Phase 4 backend configs still reject sqlite/sqlite_only authority mode"
Write-Host "  - Phase 3 reconciliation and reverse-export/restore protections remain green"
Write-Host "  - all Phase 3 tests and the complete project regression suite pass"
Write-Host "  - no production DB, private JSON, Obsidian, or completed Phase 4 files were modified"
Write-Host "  - SQLite is still shadow-read only; no authority switch was performed"
Write-Host ""
Write-Host "IMPORTANT: PASS means ready for an explicit authority-promotion implementation."
Write-Host "It does NOT mean storage_backend=sqlite has already been enabled."
exit 0
