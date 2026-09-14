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
    Write-Host " PHASE 3.1 FIX 1 GATE: BLOCKED"
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
        Stop-Gate (
            "Production SQLite runtime file already exists: $path. " +
            "Phase 3 Fix 1 tests must use temporary databases only."
        )
    }
}

Run-Step "[1/4] Phase 3.1 SQLite foundation tests" {
    & $PythonResolved -m pytest `
        tests\test_phase3_sqlite_foundation.py `
        -q
}

Run-Step "[2/4] Full regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[3/4] Python compile check" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[4/4] Git whitespace/error check" {
    git diff --check
}

foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate (
            "Gate created a production SQLite runtime file: $path"
        )
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
Write-Host " PHASE 3.1 FIX 1 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - SQLite connection policy is tested"
Write-Host "  - explicit transactions commit/rollback"
Write-Host "  - migration 0001 applies exactly once"
Write-Host "  - checksum drift is rejected"
Write-Host "  - failed migration schema changes roll back"
Write-Host "  - full regression suite remains green"
Write-Host "  - no production SQLite DB/WAL/SHM was created or tracked"
exit 0
