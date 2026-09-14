param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$BaseCommit = "0bc74663678863c8e31b4e55c3a522a12bf5ea19"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 3 FINAL GATE: BLOCKED"
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
    "personal_learning_assistant\migration\reverse_export_restore.py",
    "tests\test_phase3_reverse_export_restore.py",
    "PHASE3_2_REVERSE_EXPORT_RESTORE.md",
    "phase3_final_gate.ps1"
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required Phase 3.2 file is missing: $path"
    }
}

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

git cat-file -e "$BaseCommit^{commit}"
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Required base commit is unavailable: $BaseCommit"
}

$protectedFiles = @(
    "backup.py",
    "dashboard.py",
    "phase3_fix6_gate.ps1",
    "phase3_fix7_gate.ps1"
)
$protectedChanges = @(git diff --name-only "$BaseCommit..HEAD" -- $protectedFiles)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to compare protected files with the required base commit."
}
if ($protectedChanges.Count -ne 0) {
    Write-Host "Protected files changed:"
    Write-Host $protectedChanges
    Stop-Gate "Phase 3.2 must not modify protected Phase 3/application files."
}

$phase3Tests = @(Get-ChildItem -Path "tests" -Filter "test_phase3_*.py" -File | Sort-Object Name | ForEach-Object { $_.FullName })
if ($phase3Tests.Count -eq 0) {
    Stop-Gate "No Phase 3 test files were found under tests/."
}

Run-Step "[1/6] Phase 3.2 reverse-export and restore tests" {
    & $PythonResolved -m pytest tests\test_phase3_reverse_export_restore.py -q
}

Run-Step "[2/6] All Phase 3 tests" {
    & $PythonResolved -m pytest $phase3Tests -q
}

Run-Step "[3/6] Full regression suite" {
    & $PythonResolved -m pytest -q
}

Run-Step "[4/6] Python compile check" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[5/6] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[6/6] Git whitespace/error check from required base" {
    git diff --check "$BaseCommit..HEAD"
}

foreach ($path in $productionDbPaths) {
    if (Test-Path $path) {
        Stop-Gate "Gate created a production SQLite runtime file: $path"
    }
}

$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to check tracked private legacy JSON."
}
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host "Tracked private JSON files:"
    Write-Host $trackedPrivateJson
    Stop-Gate "Legacy private JSON authority must remain outside Git."
}

$trackedRuntimeArtifacts = @(git ls-files -- "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm" "*phase3*export*.db" "*phase3*rehearsal*.db" "*phase3*restored*.db")
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to check tracked Phase 3 runtime artifacts."
}
if ($trackedRuntimeArtifacts.Count -ne 0) {
    Write-Host "Tracked runtime artifacts:"
    Write-Host $trackedRuntimeArtifacts
    Stop-Gate "Phase 3.2 runtime databases must remain temporary and untracked."
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 3 FINAL GATE: PASS"
Write-Host "========================================="
Write-Host "Verified:"
Write-Host "  - reverse exports use isolated, new output directories"
Write-Host "  - legacy JSON, Obsidian, knowledge, and user data remain untouched"
Write-Host "  - SQLite integrity_check and foreign_key_check pass"
Write-Host "  - online backup/restore fingerprints match"
Write-Host "  - schema migrations and reverse-export re-import are idempotent"
Write-Host "  - legacy structures reconcile with explicit documented differences"
Write-Host "  - historical discrepancies remain preserved, not rewritten"
Write-Host "  - protected files and production SQLite paths remain unchanged"
Write-Host "  - Phase 4 has not begun"
exit 0
