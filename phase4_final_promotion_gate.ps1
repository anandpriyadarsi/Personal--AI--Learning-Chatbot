param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "3b7b0d1aa6d1b5844694f29ca669ff779b0f109d"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=========================================================="
    Write-Host " FINAL PHASE 4 LOCKED SQLITE PROMOTION GATE: BLOCKED"
    Write-Host "=========================================================="
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
    "personal_learning_assistant/migration/final_locked_promotion.py",
    "phase4_promote_sqlite.py",
    "tests/test_phase4_final_locked_promotion.py",
    "PHASE4_FINAL_LOCKED_SQLITE_AUTHORITY_PROMOTION.md",
    "phase4_final_promotion_gate.ps1"
)

foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required final-promotion file is missing: $path"
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
    Stop-Gate "Final promotion must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
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

$protectedFiles = @(
    "main.py",
    "config.py",
    "course_manager.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py",
    "personal_learning_assistant/migration/authority_promotion.py",
    "personal_learning_assistant/migration/compatibility_projection_seed.py",
    "personal_learning_assistant/repositories/authority_guard.py",
    "personal_learning_assistant/repositories/structured_authority_router.py",
    "personal_learning_assistant/repositories/routed_course_repository.py",
    "personal_learning_assistant/repositories/phase4_reconciliation.py",
    "personal_learning_assistant/repositories/sqlite/compatibility_repository.py",
    "personal_learning_assistant/repositories/sqlite/command_repositories.py",
    "personal_learning_assistant/repositories/sqlite/migration_runner.py",
    "personal_learning_assistant/repositories/sqlite/connection.py",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "personal_learning_assistant/repositories/question_backend.py",
    "personal_learning_assistant/repositories/question_topic_backend.py",
    "personal_learning_assistant/repositories/attempt_performance_backend.py",
    "personal_learning_assistant/repositories/learning_progress_backend.py",
    "personal_learning_assistant/repositories/study_plan_backend.py",
    "personal_learning_assistant/repositories/grade_calendar_backend.py",
    "tests/test_phase4_structured_authority_routing.py",
    "tests/test_phase4_sqlite_command_repositories.py",
    "tests/test_phase4_authority_promotion.py",
    "tests/test_phase4_final_reconciliation.py",
    "phase4_fix11_gate.ps1",
    "phase4_fix10_gate.ps1",
    "phase4_authority_promotion_gate.ps1",
    "phase4_final_gate.ps1"
)
$protectedChanges = @(git status --porcelain=v1 -- $protectedFiles)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to verify protected Phase 4 files." }
if ($protectedChanges.Count -ne 0) {
    Write-Host $protectedChanges
    Stop-Gate "Final promotion unit must not alter any Phase 4.1-4.11 implementation/foundation file."
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
    ".phase4_cutover.lock",
    ".phase4_cutover_work"
)
foreach ($path in $forbiddenRuntime) {
    if (Test-Path $path) {
        Stop-Gate "Gate must run before the real promotion and found runtime authority artifact: $path"
    }
}

# Structural safety checks before running Python.
$promotionSource = Get-Content "personal_learning_assistant/migration/final_locked_promotion.py" -Raw
$requiredTokens = @(
    "PROMOTE_PHASE4_SQLITE_AUTHORITY",
    "preflight_final_locked_promotion",
    "LocalMutationLock",
    "scan_structured_sources",
    "_run_final_imports",
    "_bridge_current_progress_history",
    "seed_phase4_compatibility_projections",
    "create_final_cutover_backup",
    "build_sqlite_authority_state",
    "write_authority_control_atomic",
    "_post_promotion_checks",
    "FinalPromotionRequiresAttention"
)
foreach ($token in $requiredTokens) {
    if ($promotionSource -notmatch [regex]::Escape($token)) {
        Stop-Gate "Final promotion implementation is missing required safety/orchestration token: $token"
    }
}
if ($promotionSource -match "if\s+__name__\s*==") {
    Stop-Gate "Promotion library must be inert on import; CLI execution belongs only in phase4_promote_sqlite.py."
}
if ($promotionSource -match "os\.remove\([^\)]*courses\.json" -or $promotionSource -match "unlink\([^\)]*courses\.json") {
    Stop-Gate "Final promotion must never delete legacy structured JSON."
}

$cliSource = Get-Content "phase4_promote_sqlite.py" -Raw
if ($cliSource -notmatch "--preflight" -or $cliSource -notmatch "--confirm") {
    Stop-Gate "Promotion CLI must expose explicit preflight and confirmation modes."
}
if ($cliSource -notmatch "CONFIRMATION_PHRASE" -or $cliSource -notmatch "args\.confirm\s*!=\s*CONFIRMATION_PHRASE") {
    Stop-Gate "Promotion CLI does not enforce the shared exact reviewed confirmation phrase."
}
if ($cliSource -notmatch 'if __name__ == "__main__"') {
    Stop-Gate "Promotion CLI must use an explicit __main__ entry point."
}

$docSource = Get-Content "PHASE4_FINAL_LOCKED_SQLITE_AUTHORITY_PROMOTION.md" -Raw
if ($docSource -notmatch "legacy structured JSON is retained" -and $docSource -notmatch "Legacy structured JSON is retained") {
    Stop-Gate "Final promotion documentation must state that legacy structured JSON is retained."
}
if ($docSource -notmatch "document_links") {
    Stop-Gate "Final promotion documentation must preserve the Phase-5 document_links boundary."
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

Run-Step "[1/17] Final locked SQLite promotion focused safety/orchestration tests" {
    & $PythonResolved -m pytest tests\test_phase4_final_locked_promotion.py -q
}
Run-Step "[2/17] Phase 4.11 structured authority routing regression" {
    & $PythonResolved -m pytest tests\test_phase4_structured_authority_routing.py -q
}
Run-Step "[3/17] Phase 4.10 SQLite command/legacy guard regression" {
    & $PythonResolved -m pytest tests\test_phase4_sqlite_command_repositories.py -q
}
Run-Step "[4/17] Phase 4.9 authority-promotion foundation regression" {
    & $PythonResolved -m pytest tests\test_phase4_authority_promotion.py -q
}
Run-Step "[5/17] Final Phase 4 reconciliation regression" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}
Run-Step "[6/17] Phase 4.8 Grades + Calendar regression" {
    & $PythonResolved -m pytest tests\test_phase4_grades_calendar_dual_read.py -q
}
Run-Step "[7/17] Phase 4.7 Study Plans regression" {
    & $PythonResolved -m pytest tests\test_phase4_study_plans_dual_read.py -q
}
Run-Step "[8/17] Phase 4.6 Learning Memory + Academic Progress regression" {
    & $PythonResolved -m pytest tests\test_phase4_learning_progress_dual_read.py -q
}
Run-Step "[9/17] Phase 4.5 Attempts/Mistakes/Performance regression" {
    & $PythonResolved -m pytest tests\test_phase4_attempts_performance_dual_read.py -q
}
Run-Step "[10/17] Phase 4.4 Question/Topic Mapping regression" {
    & $PythonResolved -m pytest tests\test_phase4_question_topic_mappings_dual_read.py -q
}
Run-Step "[11/17] Phase 4.3 Questions/Sources regression" {
    & $PythonResolved -m pytest tests\test_phase4_questions_dual_read.py -q
}
Run-Step "[12/17] Phase 4.2 Assessments regression" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}
Run-Step "[13/17] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}
Run-Step "[14/17] All Phase 3 migration/reconciliation/reverse-export regressions" {
    & $PythonResolved -m pytest $phase3Tests -q
}
Run-Step "[15/17] Full project regression suite" {
    & $PythonResolved -m pytest -q
}
Run-Step "[16/17] Python compilation and installed dependency consistency" {
    & $PythonResolved -m compileall -q .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[17/17] Git whitespace/error check and repository/private-data hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes before git diff --check." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Final promotion gate expects no pre-staged changes."
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
if ($intentAddFailed) { Stop-Gate "Unable to mark final-promotion files intent-to-add." }
if ($diffCheckFailed) { Stop-Gate "git diff --check found whitespace/errors." }

$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked private JSON." }
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host $trackedPrivateJson
    Stop-Gate "Private legacy JSON must remain untracked."
}

$trackedRuntimeArtifacts = @(git ls-files -- "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm" ".phase4_authority.json" ".phase4_cutover.lock" ".phase4_cutover_work/**" "phase4_cutover_backups/**")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked runtime artifacts." }
if ($trackedRuntimeArtifacts.Count -ne 0) {
    Write-Host $trackedRuntimeArtifacts
    Stop-Gate "Production authority, lock, work, or cutover-backup artifacts must remain untracked."
}
foreach ($path in $forbiddenRuntime) {
    if (Test-Path $path) {
        Stop-Gate "Focused/regression tests leaked a real-checkout authority artifact: $path"
    }
}

Write-Host ""
Write-Host "========================================================="
Write-Host " FINAL PHASE 4 LOCKED SQLITE PROMOTION GATE: PASS"
Write-Host "========================================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains 3b7b0d1 on phase4/structured-cutover"
Write-Host "  - promotion requires exact explicit operator confirmation"
Write-Host "  - preflight is read-only and real promotion is mutation-lock protected"
Write-Host "  - final delta imports run against an isolated SQLite candidate"
Write-Host "  - current V9 courses-shape progress history is bridged explicitly"
Write-Host "  - contradictory progress-history evidence blocks promotion"
Write-Host "  - integrity, foreign keys, migrations, ledger targets and identities are validated"
Write-Host "  - all nine Phase 4.11 compatibility projections are seeded before authority switch"
Write-Host "  - final JSON + SQLite backup is verified before install"
Write-Host "  - authority switch is atomic and legacy writes are blocked in the same control state"
Write-Host "  - pre-switch failures preserve legacy authority and restore/remove staged SQLite safely"
Write-Host "  - post-switch failures fail closed and retain the cutover lock for operator review"
Write-Host "  - Phase 4.1-4.11, Phase 3 and the complete regression suite pass"
Write-Host "  - this gate did NOT promote real user data or create production authority artifacts"
