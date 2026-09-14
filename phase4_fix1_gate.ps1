param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "5068e88f76f2792ae0f7f9244590dd4ff9018a3e"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 4.1 FIX 1 GATE: BLOCKED"
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
    "personal_learning_assistant\repositories\sqlite\course_repository.py",
    "personal_learning_assistant\repositories\course_backend.py",
    "tests\fixtures\phase4\courses.json",
    "tests\test_phase4_courses_dual_read.py",
    "PHASE4_FIX1_COURSES_TOPICS_DUAL_READ.md",
    "phase4_fix1_gate.ps1"
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 4.1 file is missing: $path"
    }
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to read the current Git branch."
}
if ($currentBranch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch."
}

git cat-file -e "$BaseCommit^{commit}"
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Required Phase 3 base commit is unavailable: $BaseCommit"
}

git merge-base --is-ancestor $BaseCommit HEAD
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Current branch is not based on required Phase 3 commit $BaseCommit."
}

$allowedChanges = @(
    "PHASE4_FIX1_COURSES_TOPICS_DUAL_READ.md",
    "phase4_fix1_gate.ps1",
    "personal_learning_assistant/repositories/course_backend.py",
    "personal_learning_assistant/repositories/sqlite/course_repository.py",
    "tests/fixtures/phase4/courses.json",
    "tests/test_phase4_courses_dual_read.py"
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
    "assessment_performance.py",
    "assessment_question_workspace.py",
    "assignment_exam_assistant.py",
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
    "academic_intelligence_dashboard.py"
)
$forbiddenChanges = @(git status --porcelain=v1 -- $forbiddenFiles)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to verify protected application files."
}
if ($forbiddenChanges.Count -ne 0) {
    Write-Host $forbiddenChanges
    Stop-Gate "Phase 4.1 scope includes Courses/Topics dual-read only."
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

Run-Step "[1/7] Phase 4.1 focused Courses/Topics dual-read tests" {
    & $PythonResolved -m pytest tests\test_phase4_courses_dual_read.py -q
}

Run-Step "[2/7] All Phase 3 regression/safety tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}

Run-Step "[3/7] Full regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[4/7] Python compilation" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[5/7] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[6/7] Git whitespace/error check from Phase 3 base"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect staged changes before git diff --check."
}
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Phase 4.1 gate expects no pre-staged changes so it can validate new untracked files safely."
}
try {
    git add --intent-to-add -- $allowedChanges
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 4.1 files intent-to-add for git diff --check."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check found whitespace/errors in the Phase 4.1 change set."
    }
}
finally {
    git reset --quiet -- $allowedChanges 2>$null
}

Write-Host ""
Write-Host "[7/7] Repository hygiene checks"
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
Write-Host " PHASE 4.1 FIX 1 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - CourseService public API remains unchanged"
Write-Host "  - legacy JSON remains authoritative for reads and writes"
Write-Host "  - SQLite Courses/Topics shadow reads are side-effect free"
Write-Host "  - semantic mismatches produce structured diagnostics"
Write-Host "  - raw identities/statuses and meaningful ordering are compared"
Write-Host "  - legacy document links remain explicit/deferred, not normalized away"
Write-Host "  - integrity_check and foreign_key_check are exercised by focused tests"
Write-Host "  - Phase 3 regression/safety tests and full regression suite pass"
Write-Host "  - no production DB/private JSON or forbidden domain changes are present"
Write-Host "  - SQLite has not been promoted to sole authority"
exit 0
