param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "f0d65b187670d526ddeaf515652f270de58247d1"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================="
    Write-Host " PHASE 5.2 DOCUMENT REGISTRY/SCANNER: BLOCKED"
    Write-Host "================================================="
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
}
else {
    $cmd = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Stop-Gate "Python interpreter not found: $Python"
    }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to read branch."
}
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}

$head = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to read HEAD."
}
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 5.2 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/source_scanner_models.py",
    "personal_learning_assistant/repositories/filesystem/source_scanner.py",
    "personal_learning_assistant/services/source_scanner_service.py",
    "phase5_scan_sources.py",
    "tests/test_phase5_document_source_scanner.py",
    "PHASE5_FIX2_DOCUMENT_REGISTRY_SOURCE_SCANNER.md",
    "phase5_fix2_gate.ps1"
)

$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
}

foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.2 file: $item"
    }
}

$status = @(git status --porcelain=v1 -uall)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect git status."
}

foreach ($line in $status) {
    if ([string]::IsNullOrWhiteSpace($line)) {
        continue
    }

    $path = $line.Substring(3).Trim().Replace("\", "/")

    if ($path.Contains(" -> ")) {
        $path = $path.Split(" -> ")[-1]
    }

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

$dbHashBefore = (
    Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256
).Hash

$controlHashBefore = (
    Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256
).Hash

$legacyHashesBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue |
ForEach-Object {
    $legacyHashesBefore[$_.FullName] = (
        Get-FileHash $_.FullName -Algorithm SHA256
    ).Hash
}

Run-Step "[1/9] Focused Phase 5.2 document/source-scanner tests" {
    & $PythonResolved -m pytest tests\test_phase5_document_source_scanner.py -q
}

Write-Host ""
Write-Host "[2/9] REAL project-document source preview (read-only)"

if (Test-Path ".\knowledge\documents" -PathType Container) {
    & $PythonResolved .\phase5_scan_sources.py `
        --database .\data\learning_assistant.db `
        --root "project-documents=.\knowledge\documents"

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Real project-document preview failed with exit code $LASTEXITCODE."
    }
}
else {
    Write-Host "knowledge\documents does not exist; real preview safely skipped."
}

Run-Step "[3/9] Phase 5.1 knowledge registry regression" {
    & $PythonResolved -m pytest tests\test_phase5_knowledge_registry_foundation.py -q
}

Run-Step "[4/9] Phase 4 post-promotion closure regression" {
    & $PythonResolved -m pytest tests\test_phase4_post_promotion_verification.py -q
}

Run-Step "[5/9] Phase 4 routing/authority safety regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py `
        -q
}

Run-Step "[6/9] Phase 3 SQLite migration regressions" {
    $phase3 = @(
        Get-ChildItem tests -File |
        Where-Object {
            $_.Name -like "test_phase3*.py"
        } |
        ForEach-Object {
            $_.FullName
        }
    )

    if ($phase3.Count -gt 0) {
        & $PythonResolved -m pytest @phase3 -q
    }
    else {
        & $PythonResolved -c "from personal_learning_assistant.repositories.sqlite.migration_runner import discover_migrations; assert len(discover_migrations()) >= 2"
    }
}

Run-Step "[7/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase5_scan_sources.py `
        tests\test_phase5_document_source_scanner.py
}

Run-Step "[8/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[9/9] Git whitespace + production/source immutability"

$staged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect staged files."
}
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.2 gate expects no pre-staged changes."
}

try {
    git add --intent-to-add -- $allowed

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 5.2 files intent-to-add."
    }

    git diff --check $BaseCommit --

    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
}
finally {
    git reset --quiet -- $allowed 2>$null
}

$dbHashAfter = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
if ($dbHashAfter -ne $dbHashBefore) {
    Stop-Gate "Phase 5.2 gate changed the authoritative SQLite database."
}

$controlHashAfter = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
if ($controlHashAfter -ne $controlHashBefore) {
    Stop-Gate "Phase 5.2 gate changed Phase 4 authority control."
}

foreach ($path in $legacyHashesBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Legacy JSON disappeared during gate: $path"
    }

    $legacyHashAfter = (Get-FileHash $path -Algorithm SHA256).Hash
    if ($legacyHashAfter -ne $legacyHashesBefore[$path]) {
        Stop-Gate "Legacy JSON changed during gate: $path"
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- `
        personal_learning_assistant/repositories/sqlite/migrations
)

if ($migrationDiff.Count -ne 0) {
    Write-Host $migrationDiff
    Stop-Gate "Phase 5.2 must not change SQLite migrations."
}

Write-Host ""
Write-Host "==============================================="
Write-Host " PHASE 5.2 DOCUMENT REGISTRY/SCANNER: PASS"
Write-Host "==============================================="
Write-Host "Verified:"
Write-Host " - deterministic supported-source discovery + raw-byte SHA-256"
Write-Host " - portable logical path keys; absolute paths are not registry identity"
Write-Host " - symlink roots/files are rejected/ignored and never followed"
Write-Host " - preview performs zero registry writes"
Write-Host " - repeated apply is idempotent on temporary SQLite"
Write-Host " - changed content preserves document identity and resets extraction state"
Write-Host " - duplicate content is flagged for review, never auto-merged"
Write-Host " - missing registered paths are reported, never auto-deleted"
Write-Host " - real project-document preview is read-only"
Write-Host " - Phase 5.1, Phase 4 closure and SQLite migration regressions pass"
Write-Host " - no migration, production SQLite, authority-control or legacy JSON bytes changed"
Write-Host ""
Write-Host "Phase 5.2 is ready for review and commit."
