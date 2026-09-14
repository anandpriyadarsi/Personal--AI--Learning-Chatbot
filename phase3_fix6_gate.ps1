param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 3.1 FIX 6 GATE: BLOCKED"
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

Run-Step "[1/5] Phase 3.1 Fix 6 questions/sources importer tests" {
    & $PythonResolved -m pytest `
        tests\test_phase3_questions_sources_importer.py `
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
Write-Host " PHASE 3.1 FIX 6 GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - verified assessment workspace reads are hash-guarded and read-only"
Write-Host "  - assessment foreign keys resolve only through Fix 5 ledger evidence"
Write-Host "  - questions and raw sources import in one transaction"
Write-Host "  - question, source, and import-batch IDs are stable UUID5 values"
Write-Host "  - raw parser units remain separate and review-required"
Write-Host "  - raw source annotations remain unresolved until human review"
Write-Host "  - question mappings and performance evidence remain deferred"
Write-Host "  - repeated identical import creates no duplicate rows"
Write-Host "  - changed hashes retain stable IDs and safely reconcile ordinals"
Write-Host "  - malformed or ambiguous input fails without partial writes"
Write-Host "  - no production SQLite DB/WAL/SHM was created or tracked"
exit 0
