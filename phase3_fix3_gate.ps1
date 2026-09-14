param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 3.1 FIX 3 GATE: BLOCKED"
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

Run-Step "[1/5] Phase 3.1 Fix 3 legacy scanner/ledger tests" {
    & $PythonResolved -m pytest tests\test_phase3_legacy_migration_tooling.py -q
}

Run-Step "[2/5] All Phase 3 tests" {
    & $PythonResolved -m pytest tests\test_phase3_*.py -q
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
Write-Host " PHASE 3.1 FIX 3 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - legacy source scans are deterministic and read-only"
Write-Host "  - source manifests use portable paths and SHA-256 hashes"
Write-Host "  - expected empty/absent sources remain explicit"
Write-Host "  - migration_imports writes are idempotent"
Write-Host "  - conflicting source-to-target mappings are rejected"
Write-Host "  - full Phase 3 and regression suites remain green"
Write-Host "  - no production SQLite DB/WAL/SHM was created or tracked"
Write-Host "  - private legacy JSON files remain untracked"
exit 0
