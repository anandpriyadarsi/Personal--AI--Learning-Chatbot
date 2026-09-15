param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "6959b06e83986b07f3a01b45ca0a3e8459d708cb"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 4.7 FIX 7 GATE: BLOCKED"
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
    if ($null -eq $PythonCommand) {
        Stop-Gate "Python interpreter was not found: $Python"
    }
    $PythonResolved = $PythonCommand.Source
}

$requiredFiles = @(
    "personal_learning_assistant\repositories\json\study_plan_repository.py",
    "personal_learning_assistant\repositories\sqlite\study_plan_repository.py",
    "personal_learning_assistant\repositories\study_plan_backend.py",
    "tests\fixtures\phase4\weekly_study_plans.json",
    "tests\fixtures\phase4\multi_course_weekly_plans.json",
    "tests\fixtures\phase4\intelligent_study_plans.json",
    "tests\test_phase4_study_plans_dual_read.py",
    "PHASE4_FIX7_STUDY_PLANS_DUAL_READ.md",
    "phase4_fix7_gate.ps1"
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 4.7 file is missing: $path"
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
    Stop-Gate "Phase 4.7 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
}

$allowedChanges = @(
    "personal_learning_assistant/repositories/json/study_plan_repository.py",
    "personal_learning_assistant/repositories/sqlite/study_plan_repository.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "tests/fixtures/phase4/weekly_study_plans.json",
    "tests/fixtures/phase4/multi_course_weekly_plans.json",
    "tests/fixtures/phase4/intelligent_study_plans.json",
    "tests/test_phase4_study_plans_dual_read.py",
    "PHASE4_FIX7_STUDY_PLANS_DUAL_READ.md",
    "phase4_fix7_gate.ps1"
)
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

$forbiddenFiles = @(
    "main.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "learning_memory.py",
    "academic_progress.py",
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "assessment_performance.py",
    "automatic_topic_mapping.py",
    "semester_grade_intelligence.py",
    "academic_calendar_planner.py",
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
    "personal_learning_assistant/repositories/json/course_repository.py",
    "personal_learning_assistant/repositories/json/assessment_repository.py",
    "personal_learning_assistant/repositories/json/question_repository.py",
    "personal_learning_assistant/repositories/json/question_topic_mapping_repository.py",
    "personal_learning_assistant/repositories/json/attempt_performance_repository.py",
    "personal_learning_assistant/repositories/json/learning_progress_repository.py",
    "personal_learning_assistant/repositories/sqlite/course_repository.py",
    "personal_learning_assistant/repositories/sqlite/assessment_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_topic_mapping_repository.py",
    "personal_learning_assistant/repositories/sqlite/attempt_performance_repository.py",
    "personal_learning_assistant/repositories/sqlite/learning_progress_repository.py",
    "personal_learning_assistant/migration/study_plans_importer.py",
    "tests/test_phase4_courses_dual_read.py",
    "tests/test_phase4_assessments_dual_read.py",
    "tests/test_phase4_questions_dual_read.py",
    "tests/test_phase4_question_topic_mappings_dual_read.py",
    "tests/test_phase4_attempts_performance_dual_read.py",
    "tests/test_phase4_learning_progress_dual_read.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected application files." }
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Phase 4.7 scope is Study Plans dual-read only."
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

Run-Step "[1/12] Phase 4.7 focused Study Plans dual-read tests" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[2/12] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[3/12] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[4/12] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[5/12] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[6/12] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[7/12] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[8/12] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[9/12] Full regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[10/12] Python compilation" {
    & $PythonResolved -m compileall -q .
}
Run-Step "[11/12] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[12/12] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.7 gate expects no pre-staged changes so new files can be validated safely."
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
if ($intentAddFailed) { Stop-Gate "Unable to mark Phase 4.7 files intent-to-add for git diff --check." }
if ($diffCheckFailed) { Stop-Gate "git diff --check found whitespace/errors in the Phase 4.7 change set." }

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
Write-Host " PHASE 4.7 FIX 7 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains 6959b06 and branch is phase4/structured-cutover"
Write-Host "  - weekly_planner.py, multi_course_planner.py, and intelligent_study_planner.py are unchanged"
Write-Host "  - weekly/multi-course/intelligent JSON stores remain authoritative"
Write-Host "  - SQLite study_plans/study_plan_items remain read-only shadow state"
Write-Host "  - saved plans are compared without rerunning planner or priority engines"
Write-Host "  - weekly, multi-course, intelligent-today, and intelligent-week identities remain distinct"
Write-Host "  - plan dates/minutes/status/engine/rationale and ordered item semantics are compared"
Write-Host "  - actual item/plan and course/topic ownership is structurally validated"
Write-Host "  - older omitted plan/item rows remain deferred historical evidence"
Write-Host "  - optional intelligent_study_plans.json absence is supported"
Write-Host "  - parity reads do not create progress snapshots or study sessions"
Write-Host "  - source bytes/hashes, SQLite rows, and connection.total_changes remain unchanged in focused tests"
Write-Host "  - integrity_check and foreign_key_check are exercised by focused tests"
Write-Host "  - Phase 4.6 through Phase 4.1, Phase 3, and full regression suites pass"
Write-Host "  - no production DB/private JSON or unrelated-domain changes are present"
Write-Host "  - SQLite has not been promoted to sole authority"
exit 0
