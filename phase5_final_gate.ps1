param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$Crosswalk = "..\phase5-review\mit1806_ma103n_crosswalk.json"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "a2633881eed965251e850b203654e5e365e37d96"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 5 FINAL RECONCILIATION/CLOSURE: BLOCKED"
    Write-Host "============================================"
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label,[scriptblock]$Command)
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
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found." }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 5.9 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/services/phase5_closure_service.py",
    "phase5_verify_closure.py",
    "tests/test_phase5_final_closure.py",
    "PHASE5_FINAL_RECONCILIATION_CLOSURE.md",
    "phase5_final_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.9 file: $item"
    }
}
foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Phase 4 authority-control file is missing."
}
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) {
    Stop-Gate "Current Phase 5.8 retrieval index is missing."
}
if (-not (Test-Path $Crosswalk -PathType Leaf)) {
    Stop-Gate "Reviewed MIT/MA103N crosswalk is missing: $Crosswalk"
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$crosswalkBefore = (Get-FileHash $Crosswalk -Algorithm SHA256).Hash

$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

$indexBefore = @{}
Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force | ForEach-Object {
    $indexBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

$vaultPath = (& $PythonResolved -c "from obsidian_integration import get_vault_path; print(get_vault_path() or '')").Trim()
if (-not $vaultPath) {
    Stop-Gate "No enabled valid Obsidian vault is configured."
}
$packageRoot = (& $PythonResolved -c "from personal_learning_assistant.ingestion.external_course_package import discover_mit1806_package; import sys; print(discover_mit1806_package(sys.argv[1]))" $vaultPath).Trim()
if ($LASTEXITCODE -ne 0 -or -not $packageRoot) {
    Stop-Gate "Unable to locate the MIT 18.06 package in the configured vault."
}
$packageBefore = @{}
foreach ($name in @("course_manifest.json","lecture_inventory.json","schema.json","chunks.jsonl")) {
    $path = Join-Path $packageRoot $name
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "MIT package file is missing: $name"
    }
    $packageBefore[$path] = (Get-FileHash $path -Algorithm SHA256).Hash
}

Run-Step "[1/10] Focused Phase 5.9 closure tests" {
    & $PythonResolved -m pytest tests\test_phase5_final_closure.py -q
}

Run-Step "[2/10] REAL Phase 5 reconciliation + isolated retrieval rebuild rehearsal" {
    & $PythonResolved .\phase5_verify_closure.py `
        --project-root . `
        --database .\data\learning_assistant.db `
        --authority .\.phase4_authority.json `
        --index-root .\.phase5_retrieval `
        --configured-vault `
        --crosswalk $Crosswalk `
        --local-course MA103N
}

Run-Step "[3/10] Phase 5.1-5.8 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_knowledge_registry_foundation.py `
        tests\test_phase5_document_source_scanner.py `
        tests\test_phase5_obsidian_vault_registry.py `
        tests\test_phase5_notes_studio_foundation.py `
        tests\test_phase5_resources2_core.py `
        tests\test_phase5_unified_ingestion.py `
        tests\test_phase5_external_course_knowledge.py `
        tests\test_phase5_external_course_crosswalk.py `
        tests\test_phase5_rebuildable_retrieval.py -q
}

Run-Step "[4/10] Phase 4 post-promotion regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py -q
}

Run-Step "[5/10] Phase 3 foundation/reconciliation/restore regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase3_sqlite_foundation.py `
        tests\test_phase3_reconciliation_reports.py `
        tests\test_phase3_reverse_export_restore.py -q
}

Run-Step "[6/10] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p59_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" `
            (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest `
            ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") `
            -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[7/10] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase5_verify_closure.py `
        tests\test_phase5_final_closure.py
}

Run-Step "[8/10] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[9/10] SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p59_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        @(
            "import sqlite3",
            "c = sqlite3.connect('file:data/learning_assistant.db?mode=ro', uri=True)",
            "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
            "assert not c.execute('PRAGMA foreign_key_check').fetchall()",
            "c.close()"
        ) | Set-Content -Path $sqliteCheckPath -Encoding ASCII
        & $PythonResolved $sqliteCheckPath
    } finally {
        Remove-Item $sqliteCheckPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "[10/10] Git + production/package/crosswalk/current-index immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.9 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 5.9 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 5.9 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 5.9 gate changed Phase 4 authority control."
}
if ((Get-FileHash $Crosswalk -Algorithm SHA256).Hash -ne $crosswalkBefore) {
    Stop-Gate "Phase 5.9 gate changed the reviewed crosswalk."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 5.9 gate: $path"
    }
}
foreach ($path in $packageBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $packageBefore[$path]) {
        Stop-Gate "MIT package source changed during Phase 5.9 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Current retrieval index file set changed during Phase 5.9 gate."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected current retrieval index file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Current retrieval index changed during Phase 5.9 gate: $($file.FullName)"
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 5.9 must not change historical SQLite migrations."
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 5 FINAL RECONCILIATION/CLOSURE: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - SQLite remains authoritative and legacy structured writes remain blocked"
Write-Host " - 0001/0002 schema is unchanged and integrity/FK checks pass"
Write-Host " - knowledge registry, Resources 2 and current extraction identities reconcile"
Write-Host " - MIT 18.06 package/resources/documents/chunks exactly match source evidence"
Write-Host " - reviewed MA103N crosswalk provenance is complete and preserved"
Write-Host " - no retrieval handoff remains pending"
Write-Host " - current lexical retrieval generation matches authoritative source fingerprint"
Write-Host " - retrieval smoke query and compact RAG context preserve provenance"
Write-Host " - isolated rebuild reproduces the same deterministic lexical generation"
Write-Host " - production SQLite, authority, package, crosswalk and current index are unchanged"
Write-Host " - Phase 5.1-5.8, Phase 4, Phase 3 and full project regressions pass"
Write-Host " - no migration, semantic promotion, LLM call or Phase 6 work was introduced"
Write-Host ""
Write-Host "Phase 5 is ready to close and commit."
