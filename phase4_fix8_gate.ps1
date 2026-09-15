param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "c97629d5e741f2c4d4a03713576b7516d649180d"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 4.8 FIX 8 GATE: BLOCKED"
    Write-Host "========================================="
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
    "personal_learning_assistant/repositories/json/grade_calendar_repository.py",
    "personal_learning_assistant/repositories/sqlite/grade_calendar_repository.py",
    "personal_learning_assistant/repositories/grade_calendar_backend.py",
    "tests/fixtures/phase4/semester_grade_config.json",
    "tests/test_phase4_grades_calendar_dual_read.py",
    "PHASE4_FIX8_GRADES_ACADEMIC_CALENDAR_DUAL_READ.md",
    "phase4_fix8_gate.ps1"
)
foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Required Phase 4.8 file is missing: $path" }
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current Git branch." }
if ($currentBranch -ne $ExpectedBranch) { Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch." }

$currentHead = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current HEAD." }
if ($currentHead -ne $BaseCommit) {
    Stop-Gate "Phase 4.8 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
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

$forbiddenFiles = @(
    "main.py",
    "semester_grade_intelligence.py",
    "academic_calendar_planner.py",
    "assignment_exam_assistant.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "learning_memory.py",
    "academic_progress.py",
    "course_manager.py",
    "assessment_question_workspace.py",
    "assessment_performance.py",
    "automatic_topic_mapping.py",
    "academic_intelligence_dashboard.py",
    "daily_academic_brief.py",
    "personal_academic_agent.py",
    "notes.py",
    "resources.py",
    "rag_answer.py",
    "semantic_retrieval.py",
    "hybrid_retrieval.py",
    "obsidian_integration.py",
    "dashboard.py",
    "personal_learning_assistant/repositories/interfaces.py",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "personal_learning_assistant/repositories/question_backend.py",
    "personal_learning_assistant/repositories/question_topic_backend.py",
    "personal_learning_assistant/repositories/attempt_performance_backend.py",
    "personal_learning_assistant/repositories/learning_progress_backend.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "personal_learning_assistant/migration/grades_calendar_importer.py",
    "tests/test_phase4_courses_dual_read.py",
    "tests/test_phase4_assessments_dual_read.py",
    "tests/test_phase4_questions_dual_read.py",
    "tests/test_phase4_question_topic_mappings_dual_read.py",
    "tests/test_phase4_attempts_performance_dual_read.py",
    "tests/test_phase4_learning_progress_dual_read.py",
    "tests/test_phase4_study_plans_dual_read.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected application files." }
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Phase 4.8 scope is Grades + Academic Calendar dual-read only."
}

$productionDbPaths = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm"
)
foreach ($path in $productionDbPaths) {
    if (Test-Path $path) { Stop-Gate "Production SQLite runtime file exists: $path" }
}

$phase3Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase3_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($phase3Tests.Count -eq 0) { Stop-Gate "No Phase 3 regression/safety tests were found." }

Run-Step "[1/13] Phase 4.8 focused Grades + Academic Calendar dual-read tests" {
    & $PythonResolved -m pytest tests\test_phase4_grades_calendar_dual_read.py -q
}
Run-Step "[2/13] Phase 4.7 Study Plans regression" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[3/13] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[4/13] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[5/13] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[6/13] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[7/13] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[8/13] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[9/13] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[10/13] Full regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[11/13] Python compilation" {
    & $PythonResolved -m compileall -q .
}
Run-Step "[12/13] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[13/13] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.8 gate expects no pre-staged changes so new files can be validated safely."
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
if ($intentAddFailed) { Stop-Gate "Unable to mark Phase 4.8 files intent-to-add for git diff --check." }
if ($diffCheckFailed) { Stop-Gate "git diff --check found whitespace/errors in the Phase 4.8 change set." }

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
    if (Test-Path $path) { Stop-Gate "Gate created or found a production SQLite runtime file: $path" }
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 4.8 FIX 8 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains c97629d and branch is phase4/structured-cutover"
Write-Host "  - semester_grade_intelligence.py, academic_calendar_planner.py, and assessment authority are unchanged"
Write-Host "  - legacy semester_grade_config.json and assessments.json remain authoritative"
Write-Host "  - SQLite grade tables and academic_events remain read-only shadow state"
Write-Host "  - planning grade scale is not silently promoted to official/verified policy"
Write-Host "  - grade scale, target SGPA, credits, manual grades, and explicit semester results are compared"
Write-Host "  - assessment deadlines are compared to source-linked academic_events without rerunning calendar algorithms"
Write-Host "  - actual semester/course/assessment/event relationships are structurally validated"
Write-Host "  - older grade/event evidence remains deferred historical evidence"
Write-Host "  - parity reads do not run SGPA projection, overload, deadline-pressure, or study-block engines"
Write-Host "  - source bytes/hashes, SQLite rows, and connection.total_changes remain unchanged in focused tests"
Write-Host "  - integrity_check and foreign_key_check are exercised by focused tests"
Write-Host "  - Phase 4.7 through Phase 4.1, Phase 3, and full regression suites pass"
Write-Host "  - no production DB/private JSON or unrelated-domain changes are present"
Write-Host "  - SQLite has not been promoted to sole authority"
exit 0
