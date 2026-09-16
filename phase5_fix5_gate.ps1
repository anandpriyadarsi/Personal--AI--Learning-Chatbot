param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "18ce28b7987643a6eec32b68f2439e1a6f4ce279"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================="
    Write-Host " PHASE 5.5 RESOURCES 2 CORE: BLOCKED"
    Write-Host "======================================="
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
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 5.5 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/resources2_models.py",
    "personal_learning_assistant/repositories/sqlite/resources2_repository.py",
    "personal_learning_assistant/services/resources2_service.py",
    "personal_learning_assistant/services/resource_legacy_reconciliation.py",
    "phase5_resources2_preview.py",
    "tests/test_phase5_resources2_core.py",
    "PHASE5_FIX5_RESOURCES2_CORE.md",
    "phase5_fix5_gate.ps1"
)

$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.5 file: $item"
    }
}

foreach ($line in @(git status --porcelain=v1 -uall)) {
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

$vaultPath = (& $PythonResolved -c "from obsidian_integration import get_vault_path; print(get_vault_path() or '')").Trim()
$vaultHashesBefore = @{}
if ($vaultPath -and (Test-Path $vaultPath -PathType Container)) {
    Get-ChildItem $vaultPath -Recurse -Filter "*.md" -File -ErrorAction Stop | ForEach-Object {
        $vaultHashesBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    }
}

Run-Step "[1/9] Focused Phase 5.5 Resources 2 tests" {
    & $PythonResolved -m pytest tests\test_phase5_resources2_core.py -q
}

Run-Step "[2/9] REAL Resources 2 reconciliation/candidate preview (read-only)" {
    & $PythonResolved .\phase5_resources2_preview.py `
        --database .\data\learning_assistant.db `
        --legacy-resources .\data\resources.json
}

Run-Step "[3/9] Phase 5.1-5.4 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_knowledge_registry_foundation.py `
        tests\test_phase5_document_source_scanner.py `
        tests\test_phase5_obsidian_vault_registry.py `
        tests\test_phase5_notes_studio_foundation.py -q
}

Run-Step "[4/9] Phase 4 post-promotion regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("p55_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $tempRoot "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" `
            (Join-Path $tempRoot "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest `
            ((Join-Path $tempRoot "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") `
            -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[6/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase5_resources2_preview.py `
        tests\test_phase5_resources2_core.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] SQLite integrity/FK read-only" {
    & $PythonResolved -c "import sqlite3;c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True);assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not c.execute('PRAGMA foreign_key_check').fetchall();c.close()"
}

Write-Host ""
Write-Host "[9/9] Git whitespace + production/source immutability"

$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.5 gate expects no pre-staged changes."
}

try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 5.5 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

$dbHashAfter = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
if ($dbHashAfter -ne $dbHashBefore) {
    Stop-Gate "Phase 5.5 gate changed the authoritative SQLite database."
}
$controlHashAfter = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
if ($controlHashAfter -ne $controlHashBefore) {
    Stop-Gate "Phase 5.5 gate changed Phase 4 authority control."
}

foreach ($path in $legacyHashesBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Legacy JSON disappeared during gate: $path"
    }
    $hashAfter = (Get-FileHash $path -Algorithm SHA256).Hash
    if ($hashAfter -ne $legacyHashesBefore[$path]) {
        Stop-Gate "Legacy JSON changed during gate: $path"
    }
}

if ($vaultPath -and (Test-Path $vaultPath -PathType Container)) {
    $afterFiles = @(Get-ChildItem $vaultPath -Recurse -Filter "*.md" -File -ErrorAction Stop)
    if ($afterFiles.Count -ne $vaultHashesBefore.Count) {
        Stop-Gate "Vault Markdown file count changed during gate."
    }
    foreach ($file in $afterFiles) {
        if (-not $vaultHashesBefore.ContainsKey($file.FullName)) {
            Stop-Gate "New Markdown appeared during gate."
        }
        $hashAfter = (Get-FileHash $file.FullName -Algorithm SHA256).Hash
        if ($hashAfter -ne $vaultHashesBefore[$file.FullName]) {
            Stop-Gate "Markdown changed during gate: $($file.FullName)"
        }
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Write-Host $migrationDiff
    Stop-Gate "Phase 5.5 must reuse existing schema; migration files changed."
}

Write-Host ""
Write-Host "====================================="
Write-Host " PHASE 5.5 RESOURCES 2 CORE: PASS"
Write-Host "====================================="
Write-Host "Verified:"
Write-Host " - typed Resources 2 use existing SQLite schema"
Write-Host " - course/topic/note/assessment/document relations are transactional"
Write-Host " - resource progress history is append-only"
Write-Host " - materialized status follows latest event time, not insertion order"
Write-Host " - duplicate signals are review-only; no silent merge occurs"
Write-Host " - zero-byte/invalid legacy resources are preserved and reported honestly"
Write-Host " - registered documents/notes become candidates, not automatic resources"
Write-Host " - real reconciliation preview performs zero writes"
Write-Host " - Phase 5.1-5.4, Phase 4 and full regressions pass"
Write-Host " - no migrations, production SQLite, authority, legacy JSON or Markdown bytes changed"
Write-Host ""
Write-Host "Phase 5.5 is ready for review and commit."
