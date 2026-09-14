param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param(
        [string]$Message
    )

    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 3.1 FIX 2 GATE: BLOCKED"
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
$requiredMigrationFiles = @(
    "personal_learning_assistant\repositories\sqlite\migrations\0001_foundation.sql",
    "personal_learning_assistant\repositories\sqlite\migrations\0002_academic_schema.sql"
)
$productionDbPaths = @(
    "data\learning_assistant.db",
    "data\learning_assistant.db-wal",
    "data\learning_assistant.db-shm"
)

foreach ($path in $requiredMigrationFiles) {
    if (-not (Test-Path $path)) {
        Stop-Gate "Required migration file is missing: $path"
    }
}

foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate (
            "Production SQLite runtime file already exists: $path. " +
            "Phase 3.1 Fix 2 verification must use temporary databases only."
        )
    }
}

Run-Step "[1/5] Phase 3.1 Fix 1 foundation tests" {
    & $PythonResolved -m pytest `
        tests\test_phase3_sqlite_foundation.py `
        -q
}

Run-Step "[2/5] Phase 3.1 Fix 2 academic schema tests" {
    & $PythonResolved -m pytest `
        tests\test_phase3_academic_schema.py `
        -q
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
    Write-Host ""
    Write-Host "Tracked production database files:"
    Write-Host $trackedDbFiles
    Stop-Gate "Production SQLite files must remain outside Git."
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 3.1 FIX 2 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - foundation and academic schema migrations are tested"
Write-Host "  - schema integrity and foreign keys are clean"
Write-Host "  - core academic relationships and constraints are enforced"
Write-Host "  - stable SQL read models behave as expected"
Write-Host "  - Markdown bodies and semantic vectors stay outside core SQLite"
Write-Host "  - full regression suite remains green"
Write-Host "  - no production SQLite DB/WAL/SHM was created or tracked"
exit 0
