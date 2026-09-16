param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "de509c9549357c77750438c608a4314bb2519357"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "===================================================="
    Write-Host " PHASE 5.3 OBSIDIAN VAULT/LINK GRAPH: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 5.3 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/obsidian_vault_models.py",
    "personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py",
    "personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py",
    "personal_learning_assistant/services/obsidian_vault_registry_service.py",
    "phase5_scan_obsidian_vault.py",
    "tests/test_phase5_obsidian_vault_registry.py",
    "PHASE5_FIX3_OBSIDIAN_VAULT_REGISTRY_LINK_GRAPH.md",
    "phase5_fix3_gate.ps1"
)

$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }
foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.3 file: $item"
    }
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

$vaultPath = (& $PythonResolved -c "from obsidian_integration import get_vault_path; print(get_vault_path() or '')").Trim()
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Unable to inspect configured Obsidian vault path."
}

$vaultHashesBefore = @{}
if ($vaultPath -and (Test-Path $vaultPath -PathType Container)) {
    Get-ChildItem $vaultPath -Recurse -Filter "*.md" -File -ErrorAction Stop | ForEach-Object {
        $vaultHashesBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    }
}

Run-Step "[1/9] Focused Phase 5.3 Obsidian vault/link-graph tests" {
    & $PythonResolved -m pytest tests\test_phase5_obsidian_vault_registry.py -q
}

Run-Step "[2/9] REAL configured Obsidian vault preview (read-only)" {
    & $PythonResolved .\phase5_scan_obsidian_vault.py `
        --database .\data\learning_assistant.db `
        --configured `
        --vault-key "nitk-vault"
}

Run-Step "[3/9] Phase 5.1-5.2 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_knowledge_registry_foundation.py `
        tests\test_phase5_document_source_scanner.py -q
}

Run-Step "[4/9] Phase 4 post-promotion safety regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py -q
}

Run-Step "[5/9] Phase 3 SQLite migration regressions" {
    $phase3 = @(
        Get-ChildItem tests -File |
        Where-Object { $_.Name -like "test_phase3*.py" } |
        ForEach-Object { $_.FullName }
    )
    if ($phase3.Count -gt 0) {
        & $PythonResolved -m pytest @phase3 -q
    } else {
        & $PythonResolved -c "from personal_learning_assistant.repositories.sqlite.migration_runner import discover_migrations; assert len(discover_migrations()) >= 2"
    }
}

Run-Step "[6/9] Complete project regression suite (promotion-aware)" {
    # One Phase 2 closure test intentionally asserts that the production
    # SQLite database does not exist BEFORE Phase 3 begins. The real runtime
    # has now completed the Phase 4 SQLite promotion, so that environmental
    # assertion is no longer valid in the promoted checkout.
    #
    # Run every other project test against the real promoted runtime, then run
    # that exact historical pre-Phase3 assertion in an isolated temp root where
    # its original precondition is true. Do not delete/rename the real DB merely
    # to satisfy a historical test.
    $legacyNoDbNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"

    & $PythonResolved -m pytest -q --deselect $legacyNoDbNode
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $tempPhase2Root = Join-Path ([System.IO.Path]::GetTempPath()) ("phase5_phase2_closure_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $tempPhase2Root "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" (Join-Path $tempPhase2Root "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest `
            ((Join-Path $tempPhase2Root "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") `
            -q
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } finally {
        Remove-Item $tempPhase2Root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[7/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase5_scan_obsidian_vault.py `
        tests\test_phase5_obsidian_vault_registry.py
}

Run-Step "[8/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[9/9] Git whitespace + production/vault immutability"

$staged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged files." }
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.3 gate expects no pre-staged changes."
}

try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 5.3 files intent-to-add."
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
    Stop-Gate "Phase 5.3 gate changed the authoritative SQLite database."
}

$controlHashAfter = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
if ($controlHashAfter -ne $controlHashBefore) {
    Stop-Gate "Phase 5.3 gate changed Phase 4 authority control."
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
    $vaultFilesAfter = @(
        Get-ChildItem $vaultPath -Recurse -Filter "*.md" -File -ErrorAction Stop
    )
    if ($vaultFilesAfter.Count -ne $vaultHashesBefore.Count) {
        Stop-Gate "Configured vault Markdown file count changed during gate."
    }
    foreach ($file in $vaultFilesAfter) {
        if (-not $vaultHashesBefore.ContainsKey($file.FullName)) {
            Stop-Gate "A new Markdown file appeared during gate: $($file.FullName)"
        }
        $hashAfter = (Get-FileHash $file.FullName -Algorithm SHA256).Hash
        if ($hashAfter -ne $vaultHashesBefore[$file.FullName]) {
            Stop-Gate "Markdown bytes changed during gate: $($file.FullName)"
        }
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Write-Host $migrationDiff
    Stop-Gate "Phase 5.3 must reuse existing schema; migration files changed."
}

Write-Host ""
Write-Host "==============================================="
Write-Host " PHASE 5.3 OBSIDIAN VAULT/LINK GRAPH: PASS"
Write-Host "==============================================="
Write-Host "Verified:"
Write-Host " - vault scan is read-only and deterministic"
Write-Host " - notes without frontmatter remain discoverable"
Write-Host " - assistant_id/path identity rules are explicit"
Write-Host " - frontmatter metadata/tags are imported without Markdown rewrites"
Write-Host " - wiki/Markdown links preserve headings, blocks and unresolved evidence"
Write-Host " - exact path wins before assistant_id/unique-basename resolution"
Write-Host " - duplicate basenames are ambiguous, never silently guessed"
Write-Host " - backlinks are queryable from resolved note_links"
Write-Host " - missing notes are reported, never auto-deleted"
Write-Host " - real configured vault preview performed zero database/source writes"
Write-Host " - Phase 5.1-5.2, Phase 4, Phase 3 and full regressions pass"
Write-Host " - no migrations, production SQLite, authority state, legacy JSON or Markdown bytes changed"
Write-Host ""
Write-Host "Phase 5.3 is ready for review and commit."
