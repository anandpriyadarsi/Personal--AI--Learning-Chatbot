param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "fc8d44328d5906927c77c2d302874885a7514767"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 4.2 FIX 2 GATE: BLOCKED"
    Write-Host "========================================="
    Write-Host $Message
    exit 1
}

function Run-Step {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
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
    "personal_learning_assistant\repositories\interfaces.py",
    "personal_learning_assistant\repositories\json\assessment_repository.py",
    "personal_learning_assistant\repositories\sqlite\assessment_repository.py",
    "personal_learning_assistant\repositories\assessment_backend.py",
    "tests\fixtures\phase4\assessments.json",
    "tests\test_phase4_assessments_dual_read.py",
    "PHASE4_FIX2_ASSESSMENTS_DUAL_READ.md",
    "phase4_fix2_gate.ps1"
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 4.2 file is missing: $path"
    }
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to read the current Git branch."
}
if ($currentBranch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch."
}

$currentHead = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to read current HEAD."
}
if ($currentHead -ne $BaseCommit) {
    Stop-Gate "Phase 4.2 must remain uncommitted while gating. Expected HEAD $BaseCommit but found $currentHead."
}

$allowedChanges = @(
    "personal_learning_assistant/repositories/interfaces.py",
    "personal_learning_assistant/repositories/json/assessment_repository.py",
    "personal_learning_assistant/repositories/sqlite/assessment_repository.py",
    "personal_learning_assistant/repositories/assessment_backend.py",
    "tests/fixtures/phase4/assessments.json",
    "tests/test_phase4_assessments_dual_read.py",
    "PHASE4_FIX2_ASSESSMENTS_DUAL_READ.md",
    "phase4_fix2_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowedChanges) {
    $allowedSet[$item] = $true
}

$statusLines = @(git status --porcelain=v1 -uall)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect repository status."
}
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    $path = $line.Substring(3).Trim()
    if ($path.Contains(" -> ")) {
        $path = $path.Split(" -> ")[-1]
    }
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
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    foreach ($prefix in $protectedPrefixes) {
        if ($path.StartsWith($prefix)) {
            Stop-Gate "Protected user/source-data path changed: $path"
        }
    }
}

$forbiddenFiles = @(
    "main.py",
    "assignment_exam_assistant.py",
    "assessment_question_workspace.py",
    "assessment_performance.py",
    "automatic_topic_mapping.py",
    "learning_memory.py",
    "academic_progress.py",
    "weekly_planner.py",
    "multi_course_planner.py",
    "intelligent_study_planner.py",
    "semester_grade_intelligence.py",
    "academic_calendar_planner.py",
    "notes.py",
    "resources.py",
    "rag_answer.py",
    "obsidian_integration.py",
    "dashboard.py",
    "academic_intelligence_dashboard.py",
    "personal_learning_assistant/services/course_service.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to verify protected application files."
}
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Phase 4.2 scope is Assessments + Assessment Topics dual-read only."
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

Run-Step "[1/8] Phase 4.2 focused Assessments dual-read tests" {
    & $PythonResolved -m pytest tests\test_phase4_assessments_dual_read.py -q
}

Run-Step "[2/8] Phase 4.1 Courses/Topics regression" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}

Run-Step "[3/8] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}

Run-Step "[4/8] Full regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[5/8] Python compilation" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[6/8] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[7/8] Git whitespace/error check from Phase 4.1 base"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect staged changes before git diff --check."
}
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.2 gate expects no pre-staged changes so it can validate new files safely."
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
        if ($LASTEXITCODE -ne 0) {
            $diffCheckFailed = $true
        }
    }
}
finally {
    git reset --quiet -- $allowedChanges 2>$null
}
if ($intentAddFailed) {
    Stop-Gate "Unable to mark Phase 4.2 files intent-to-add for git diff --check."
}
if ($diffCheckFailed) {
    Stop-Gate "git diff --check found whitespace/errors in the Phase 4.2 change set."
}

Write-Host ""
Write-Host "[8/8] Repository hygiene checks"
$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect tracked private JSON."
}
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host $trackedPrivateJson
    Stop-Gate "Private legacy JSON must remain untracked."
}

$trackedRuntimeArtifacts = @(git ls-files -- "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm" "*.db" "*.db-wal" "*.db-shm")
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect tracked SQLite runtime artifacts."
}
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
Write-Host "========================================="
Write-Host " PHASE 4.2 FIX 2 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - baseline HEAD remains fc8d443 and branch is phase4/structured-cutover"
Write-Host "  - legacy assignment_exam_assistant.py public functions/writers are unchanged"
Write-Host "  - legacy assessments JSON remains authoritative for reads and writes"
Write-Host "  - SQLite Assessments/Assessment Topics is read-only shadow state"
Write-Host "  - semantic/raw/order/relationship mismatches produce structured diagnostics"
Write-Host "  - assessment course_credits remain explicit/deferred"
Write-Host "  - resolved topic IDs are structurally validated but not promoted to legacy authority"
Write-Host "  - integrity_check and foreign_key_check are exercised by focused tests"
Write-Host "  - Phase 4.1, Phase 3, and full regression suites pass"
Write-Host "  - no production DB/private JSON or later-domain changes are present"
Write-Host "  - SQLite has not been promoted to sole authority"
exit 0
