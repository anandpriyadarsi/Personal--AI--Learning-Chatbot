param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Stop-Gate {
    param(
        [string]$Message,
        [int]$Code = 1
    )

    Write-Host ""
    Write-Host "========================================="
    Write-Host " PHASE 2 CLOSURE GATE: BLOCKED"
    Write-Host "========================================="
    Write-Host $Message
    exit $Code
}

function Invoke-GateStep {
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

function Get-JsonManifest {
    $manifest = @{}

    if (-not (Test-Path ".\data")) {
        return $manifest
    }

    Get-ChildItem ".\data" -Recurse -File -Filter "*.json" |
        Sort-Object FullName |
        ForEach-Object {
            $relative = Resolve-Path $_.FullName -Relative
            $hash = (
                Get-FileHash $_.FullName -Algorithm SHA256
            ).Hash

            $manifest[$relative] = (
                "$($_.Length):$hash"
            )
        }

    return $manifest
}

function Compare-Manifests {
    param(
        [hashtable]$Before,
        [hashtable]$After
    )

    $changes = @()

    $allKeys = @(
        $Before.Keys
        $After.Keys
    ) | Sort-Object -Unique

    foreach ($key in $allKeys) {
        if (-not $Before.ContainsKey($key)) {
            $changes += "CREATED $key"
            continue
        }

        if (-not $After.ContainsKey($key)) {
            $changes += "DELETED $key"
            continue
        }

        if ($Before[$key] -ne $After[$key]) {
            $changes += "CHANGED $key"
        }
    }

    return $changes
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 2 FIX 19 - CLOSURE GATE"
Write-Host "========================================="
Write-Host ""
Write-Host "Purpose:"
Write-Host "  Prove the Phase 2 service/current-storage boundary"
Write-Host "  before any Phase 3 SQLite migration work begins."
Write-Host ""

if (-not (Test-Path $Python)) {
    Stop-Gate "Python virtual environment not found at $Python"
}

if (-not (Test-Path ".\tests\test_phase2_closure_architecture.py")) {
    Stop-Gate "tests\test_phase2_closure_architecture.py is missing."
}

# Capture the authoritative JSON state before any test command runs.
$beforeJson = Get-JsonManifest

Invoke-GateStep "[1/8] Dependency integrity" {
    & $Python -m pip check
}

Invoke-GateStep "[2/8] Phase 2 architecture closure tests" {
    & $Python -m pytest `
        tests\test_phase2_closure_architecture.py `
        -q
}

Invoke-GateStep "[3/8] Complete Phase 2 regression slice" {
    & $Python -m pytest tests -q -k "phase2"
}

Invoke-GateStep "[4/8] Read-only query/fixture tests" {
    & $Python -m pytest tests -q -m "read_only"
}

Invoke-GateStep "[5/8] Full regression suite" {
    & $Python -m pytest -q
}

# The official Phase 2 gate requires read queries/tests to leave
# authoritative JSON unchanged. Compare byte hashes and file membership.
$afterJson = Get-JsonManifest
$jsonChanges = Compare-Manifests `
    -Before $beforeJson `
    -After $afterJson

if ($jsonChanges.Count -gt 0) {
    Write-Host ""
    Write-Host "Authoritative JSON changed during the gate:"
    $jsonChanges | ForEach-Object {
        Write-Host "  $_"
    }

    Stop-Gate (
        "Phase 2 read/query gate failed because data/*.json " +
        "did not remain byte-for-byte unchanged."
    )
}

Write-Host ""
Write-Host "Authoritative JSON hash check: PASS"

Invoke-GateStep "[6/8] Python compile check" {
    & $Python -m compileall -q .
}

Invoke-GateStep "[7/8] V13 startup smoke test" {
    "40" | & $Python main.py
}

Invoke-GateStep "[8/8] Git whitespace/error check" {
    git diff --check
}

# Security/authority checks are hard blockers.
$trackedEnv = git ls-files -- ".env"
if ($trackedEnv) {
    Stop-Gate ".env is tracked by Git. Remove it from source control before Phase 3."
}

$trackedDb = git ls-files -- "data/learning_assistant.db"
if ($trackedDb) {
    Stop-Gate "data/learning_assistant.db is already tracked. Phase 3 has started prematurely."
}

if (Test-Path ".\data\learning_assistant.db") {
    Stop-Gate "data/learning_assistant.db already exists. Review/remove it before declaring Phase 2 closed."
}

Write-Host ""
Write-Host "========================================="
Write-Host " PHASE 2 CLOSURE: PASS"
Write-Host "========================================="
Write-Host ""
Write-Host "The Phase 2 code/test gate is green:"
Write-Host "  - service/repository dependency direction verified"
Write-Host "  - service layer remains non-interactive"
Write-Host "  - selected compatibility facades remain present"
Write-Host "  - JSON/current files remain authoritative"
Write-Host "  - authoritative JSON hashes stayed unchanged"
Write-Host "  - Phase 2 tests passed"
Write-Host "  - full regression suite passed"
Write-Host "  - V13 startup smoke test passed"
Write-Host ""

# Secondary pre-Phase-3 readiness checks.
# These do not invalidate the Phase 2 architecture pass, but they must be
# resolved before we actually start Phase 3 migration tooling.
$readinessWarnings = @()

if (-not (Test-Path ".\.gitattributes")) {
    $readinessWarnings += (
        ".gitattributes is missing; Windows line-ending policy is not locked."
    )
}

$fixtureJsonCount = 0
if (Test-Path ".\tests\fixtures") {
    $fixtureJsonCount = @(
        Get-ChildItem ".\tests\fixtures" `
            -Recurse `
            -File `
            -Filter "*.json"
    ).Count
}

if ($fixtureJsonCount -eq 0) {
    $readinessWarnings += (
        "No tracked JSON fixtures were found under tests/fixtures; " +
        "the clean-clone/private-data independence gate is not proven."
    )
}

$workingTree = git status --short
if ($workingTree) {
    $readinessWarnings += (
        "Git working tree is not clean. Commit/review the intended Fix 19 files and rerun."
    )
}

$upstream = $null
try {
    $upstream = (
        git rev-parse `
            --abbrev-ref `
            --symbolic-full-name `
            "@{u}" 2>$null
    )
}
catch {
    $upstream = $null
}

if (-not $upstream) {
    $readinessWarnings += (
        "Current branch has no verified upstream; remote recoverability is not proven."
    )
}

if ($readinessWarnings.Count -gt 0) {
    Write-Host "========================================="
    Write-Host " PRE-PHASE 3 READINESS: PENDING"
    Write-Host "========================================="

    foreach ($warning in $readinessWarnings) {
        Write-Host "  - $warning"
    }

    Write-Host ""
    Write-Host (
        "Exit code 2 means Phase 2 architecture/tests passed, " +
        "but one or more release/readiness items still need attention."
    )
    exit 2
}

Write-Host "========================================="
Write-Host " PRE-PHASE 3 READINESS: PASS"
Write-Host "========================================="
Write-Host ""
Write-Host "Phase 2 is closed and the repository is ready to begin Phase 3 planning."
exit 0
