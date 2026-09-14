param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 3.1 FIX 9 GATE: BLOCKED"
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

if (-not (Test-Path $Python)) {
    Stop-Gate "Python virtual environment not found at $Python"
}

$PythonResolved = (Resolve-Path $Python).Path
$productionDbPaths = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm"
)

foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate "Production SQLite runtime file already exists: $path"
    }
}

$phase3Tests = @(
    Get-ChildItem `
        -Path "tests" `
        -Filter "test_phase3_*.py" `
        -File |
        Sort-Object Name |
        ForEach-Object { $_.FullName }
)

if ($phase3Tests.Count -eq 0) {
    Stop-Gate "No Phase 3 test files were found under tests/."
}

Run-Step "[1/5] Phase 3.1 Fix 9 learning-memory/progress tests" {
    & $PythonResolved -m pytest `
        tests\test_phase3_learning_progress_importer.py `
        -q
}

Run-Step "[2/5] All Phase 3 tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}

Run-Step "[3/5] Full regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[4/5] Python compile check" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[5/5] Git whitespace/error check" {
    git diff --check
}

foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate "Gate created a production SQLite runtime file: $path"
    }
}

$trackedDbFiles = git ls-files -- `
    "data/learning_assistant.db" `
    "data/learning_assistant.db-wal" `
    "data/learning_assistant.db-shm"
if ($trackedDbFiles) {
    Stop-Gate "Production SQLite files must remain outside Git."
}

$trackedPrivateJson = git ls-files -- "data/*.json" "data/**/*.json"
if ($trackedPrivateJson) {
    Write-Host "Tracked private JSON files:"
    Write-Host $trackedPrivateJson
    Stop-Gate "Legacy private JSON authority must remain outside Git."
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 3.1 FIX 9 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - learning_memory.json imports as append-only memory evidence"
Write-Host "  - course_progress_history.json imports as progress snapshots"
Write-Host "  - weak/mastered memory can create topic-progress evidence only when exact topic resolution exists"
Write-Host "  - unresolved topics/courses remain reviewable and are not guessed"
Write-Host "  - identical re-import is idempotent"
Write-Host "  - changed source hashes update stable targets and record new ledger evidence"
Write-Host "  - source changes after scan are rejected before writes"
Write-Host "  - full Phase 3 and regression suites remain green"
Write-Host "  - no production SQLite DB/WAL/SHM was created or tracked"
Write-Host "  - private legacy JSON files remain untracked"
exit 0
