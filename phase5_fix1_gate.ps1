param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "58fbab8fe57fb34e58979c95714f00a42e7a0a2f"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "===================================================="
    Write-Host " PHASE 5.1 KNOWLEDGE REGISTRY FOUNDATION: BLOCKED"
    Write-Host "===================================================="
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
} else {
    $cmd = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found: $Python" }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read branch." }
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read HEAD." }
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 5.1 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/knowledge_registry_models.py",
    "personal_learning_assistant/repositories/sqlite/knowledge_registry_repository.py",
    "personal_learning_assistant/services/knowledge_registry_service.py",
    "personal_learning_assistant/services/operation_coordination_service.py",
    "phase5_verify_registry.py",
    "tests/test_phase5_knowledge_registry_foundation.py",
    "PHASE5_FIX1_KNOWLEDGE_REGISTRY_FOUNDATION.md",
    "phase5_fix1_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }
foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing Phase 5.1 file: $item" }
}
$status = @(git status --porcelain=v1 -uall)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect git status." }
foreach ($line in $status) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\", "/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope source change detected: $path"
    }
}

if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Promoted Phase 4 authority-control file is missing."
}
if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Promoted SQLite database is missing."
}

$dbHashBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$controlHashBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacyHashesBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyHashesBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/8] Focused Phase 5.1 registry/journal/outbox tests" {
    & $PythonResolved -m pytest tests\test_phase5_knowledge_registry_foundation.py -q
}

Run-Step "[2/8] REAL promoted SQLite registry readiness (read-only)" {
    & $PythonResolved .\phase5_verify_registry.py --database .\data\learning_assistant.db
}

Run-Step "[3/8] Phase 4 post-promotion closure regression" {
    & $PythonResolved -m pytest tests\test_phase4_post_promotion_verification.py -q
}

Run-Step "[4/8] Phase 4 routing + authority safety regressions" {
    & $PythonResolved -m pytest tests\test_phase4_structured_authority_routing.py tests\test_phase4_authority_promotion.py -q
}

Run-Step "[5/8] SQLite migration foundation regressions" {
    $phase3 = @(Get-ChildItem tests -File | Where-Object { $_.Name -like "test_phase3*.py" } | ForEach-Object { $_.FullName })
    if ($phase3.Count -gt 0) {
        & $PythonResolved -m pytest @phase3 -q
    } else {
        & $PythonResolved -c "from personal_learning_assistant.repositories.sqlite.migration_runner import discover_migrations; assert len(discover_migrations()) >= 2"
    }
}

Run-Step "[6/8] Python compilation" {
    & $PythonResolved -m compileall -q personal_learning_assistant phase5_verify_registry.py tests\test_phase5_knowledge_registry_foundation.py
}

Run-Step "[7/8] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[8/8] Git whitespace + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged files." }
if ($staged.Count -ne 0) { Stop-Gate "Phase 5.1 gate expects no pre-staged changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 5.1 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbHashBefore) {
    Stop-Gate "Phase 5.1 gate changed the authoritative SQLite database."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $controlHashBefore) {
    Stop-Gate "Phase 5.1 gate changed Phase 4 authority control."
}
foreach ($path in $legacyHashesBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Legacy JSON disappeared during gate: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyHashesBefore[$path]) {
        Stop-Gate "Legacy JSON changed during gate: $path"
    }
}

$migrationDiff = @(git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations)
if ($migrationDiff.Count -ne 0) {
    Write-Host $migrationDiff
    Stop-Gate "Phase 5.1 must reuse existing schema; migration files changed unexpectedly."
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 5.1 KNOWLEDGE REGISTRY FOUNDATION: PASS"
Write-Host "=================================================="
Write-Host "Verified:"
Write-Host " - Phase 4 promoted SQLite remains unchanged/authoritative"
Write-Host " - existing 0001/0002 schema is sufficient; no new migration added"
Write-Host " - explicit-connection knowledge registry validates documents/chunks/index jobs"
Write-Host " - stable document IDs and idempotent registration are covered"
Write-Host " - content revision preserves identity and invalidates extraction state"
Write-Host " - chunk replacement and index jobs are transactional/deterministic"
Write-Host " - operation journal state machine is explicit"
Write-Host " - outbox events are canonical JSON with explicit terminal states"
Write-Host " - real registry readiness check is read-only"
Write-Host " - no legacy JSON, authority control, or production SQLite bytes changed"
Write-Host ""
Write-Host "Phase 5.1 is ready for review and commit."
