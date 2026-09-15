param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "0a92938ba468bd78d8188e45a661a080c85f1f8e"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================"
    Write-Host " PHASE 4.11 STRUCTURED AUTHORITY ROUTING GATE: BLOCKED"
    Write-Host "======================================================"
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
    "personal_learning_assistant/repositories/structured_authority_router.py",
    "personal_learning_assistant/repositories/routed_course_repository.py",
    "personal_learning_assistant/repositories/sqlite/compatibility_repository.py",
    "personal_learning_assistant/migration/compatibility_projection_seed.py",
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py",
    "tests/test_phase4_structured_authority_routing.py",
    "PHASE4_11_STRUCTURED_AUTHORITY_ROUTING.md",
    "phase4_fix11_gate.ps1"
)

foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 4.11 file is missing: $path"
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
    Stop-Gate "Phase 4.11 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
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

# Phase 4.11 is a routing unit. It must not weaken the prior migration,
# reconciliation, shadow-read, command-write, or authority-control foundations.
$protectedFiles = @(
    "main.py",
    "config.py",
    "automatic_topic_mapping.py",
    "assessment_performance.py",
    "academic_calendar_planner.py",
    "personal_learning_assistant/migration/authority_promotion.py",
    "personal_learning_assistant/repositories/authority_guard.py",
    "personal_learning_assistant/repositories/interfaces.py",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "personal_learning_assistant/repositories/question_backend.py",
    "personal_learning_assistant/repositories/question_topic_backend.py",
    "personal_learning_assistant/repositories/attempt_performance_backend.py",
    "personal_learning_assistant/repositories/learning_progress_backend.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "personal_learning_assistant/repositories/grade_calendar_backend.py",
    "personal_learning_assistant/repositories/sqlite/command_repositories.py",
    "personal_learning_assistant/repositories/sqlite/course_repository.py",
    "personal_learning_assistant/repositories/sqlite/assessment_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_repository.py",
    "personal_learning_assistant/repositories/sqlite/question_topic_mapping_repository.py",
    "personal_learning_assistant/repositories/sqlite/attempt_performance_repository.py",
    "personal_learning_assistant/repositories/sqlite/learning_progress_repository.py",
    "personal_learning_assistant/repositories/sqlite/study_plan_repository.py",
    "personal_learning_assistant/repositories/sqlite/grade_calendar_repository.py",
    "personal_learning_assistant/repositories/json/course_repository.py",
    "personal_learning_assistant/repositories/json/assessment_repository.py",
    "personal_learning_assistant/repositories/json/question_repository.py",
    "personal_learning_assistant/repositories/json/learning_progress_repository.py",
    "personal_learning_assistant/repositories/json/study_plan_repository.py",
    "personal_learning_assistant/repositories/json/grade_calendar_repository.py",
    "tests/test_phase4_sqlite_command_repositories.py",
    "tests/test_phase4_authority_promotion.py",
    "tests/test_phase4_final_reconciliation.py",
    "phase4_fix10_gate.ps1",
    "phase4_authority_promotion_gate.ps1",
    "phase4_final_gate.ps1"
)
$protectedChanges = @(git status --porcelain=v1 -- $protectedFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected Phase 4 files." }
if ($protectedChanges.Count -ne 0) {
    Write-Host $protectedChanges
    Stop-Gate "Phase 4.11 must not alter prior command, guard, shadow, migration, or reconciliation foundations."
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
    if (Test-Path $path) { Stop-Gate "Phase 4.11 must not create runtime authority artifact: $path" }
}

# Cheap structural checks before running tests.
$routerSource = Get-Content "personal_learning_assistant/repositories/structured_authority_router.py" -Raw
if ($routerSource -notmatch "mode=rw") {
    Stop-Gate "Structured router must use SQLite mode=rw so a missing production DB cannot be silently created."
}
if ($routerSource -match "write_authority_control_atomic" -or $routerSource -match "build_sqlite_authority_state") {
    Stop-Gate "Phase 4.11 router must not perform the authority switch."
}
if ($routerSource -notmatch "maybe_load_sqlite_structured_store" -or $routerSource -notmatch "maybe_save_sqlite_structured_store") {
    Stop-Gate "Structured router does not expose the expected read/write compatibility entry points."
}

$compatSource = Get-Content "personal_learning_assistant/repositories/sqlite/compatibility_repository.py" -Raw
if ($compatSource -match "write_authority_control_atomic" -or $compatSource -match "build_sqlite_authority_state") {
    Stop-Gate "Compatibility repository must not write authority-control state."
}
if ($compatSource -match "sqlite3\.connect\(" -or $compatSource -match "connect_database\(") {
    Stop-Gate "Compatibility repository must use only its explicitly supplied SQLite connection."
}
if ($compatSource -notmatch "BEGIN IMMEDIATE" -or $compatSource -notmatch "rollback") {
    Stop-Gate "Compatibility repository does not visibly provide transactional rollback semantics."
}

$seedSource = Get-Content "personal_learning_assistant/migration/compatibility_projection_seed.py" -Raw
if ($seedSource -match "write_authority_control_atomic" -or $seedSource -match "build_sqlite_authority_state") {
    Stop-Gate "Projection seed must remain pre-promotion and must not flip authority."
}
if ($seedSource -match "sqlite3\.connect\(" -or $seedSource -match "connect_database\(") {
    Stop-Gate "Projection seed must use only an explicitly supplied SQLite connection."
}

$courseRouting = Get-Content "personal_learning_assistant/repositories/routed_course_repository.py" -Raw
if ($courseRouting -match "(^|\n)\s*(import|from)\s+course_manager(\s|\.|$)") {
    Stop-Gate "Routed course repository reintroduced the forbidden Phase 2 dependency on root course_manager."
}

$routedProceduralFiles = @(
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
foreach ($path in $routedProceduralFiles) {
    $text = Get-Content $path -Raw
    if ($text -notmatch "maybe_load_sqlite_structured_store" -or $text -notmatch "maybe_save_sqlite_structured_store") {
        Stop-Gate "Compatibility module is missing Phase 4.11 authority routing: $path"
    }
    if ($text -notmatch "guard_legacy_structured_write" -or $text -notmatch "infer_authority_control_path") {
        Stop-Gate "Phase 4.10 legacy fail-closed guard was lost while routing: $path"
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

Run-Step "[1/16] Phase 4.11 structured authority routing + compatibility cutover tests" {
    & $PythonResolved -m pytest tests\test_phase4_structured_authority_routing.py -q
}
Run-Step "[2/16] Phase 4.10 SQLite command/legacy guard regression" {
    & $PythonResolved -m pytest tests\test_phase4_sqlite_command_repositories.py -q
}
Run-Step "[3/16] Phase 4.9 authority-promotion foundation regression" {
    & $PythonResolved -m pytest tests\test_phase4_authority_promotion.py -q
}
Run-Step "[4/16] Final Phase 4 reconciliation regression" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}
Run-Step "[5/16] Phase 4.8 Grades + Calendar regression" {
    & $PythonResolved -m pytest tests\test_phase4_grades_calendar_dual_read.py -q
}
Run-Step "[6/16] Phase 4.7 Study Plans regression" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[7/16] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[8/16] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[9/16] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[10/16] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[11/16] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[12/16] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[13/16] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[14/16] Full project regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[15/16] Python compilation and installed dependency consistency" {
    & $PythonResolved -m compileall -q .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[16/16] Git whitespace/error check and repository hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.11 gate expects no pre-staged changes."
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
if ($intentAddFailed) { Stop-Gate "Unable to mark Phase 4.11 files intent-to-add." }
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
Write-Host "====================================================="
Write-Host " PHASE 4.11 STRUCTURED AUTHORITY ROUTING GATE: PASS"
Write-Host "====================================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains 0a92938 on phase4/structured-cutover"
Write-Host "  - missing/legacy/dual-read authority preserves existing JSON behavior"
Write-Host "  - SQLite authority routes compatibility reads/writes to an already-existing mode=rw database"
Write-Host "  - SQLite routing never silently creates the production database"
Write-Host "  - exact compatibility projections and normalized relational updates commit together"
Write-Host "  - final compatibility seed is pre-promotion only and uses the locked structured source manifest"
Write-Host "  - CourseService uses RoutedCourseRepository without reintroducing root course_manager dependency"
Write-Host "  - Phase-5 course document_links remain explicit legacy-read-only/deferred state"
Write-Host "  - post-promotion legacy structured bytes are not used as write fallback"
Write-Host "  - Phase 4.10 command/guard surface and Phase 4.1-4.9 foundations remain unchanged"
Write-Host "  - Phase 4.1-4.10, final reconciliation, Phase 3 and full regressions pass"
Write-Host "  - no production DB/control/lock/private-data artifact was created or tracked"
Write-Host "  - production authority has NOT been switched by Phase 4.11"
exit 0
