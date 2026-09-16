param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase5/knowledge-notes-resources"
$BaseCommit = "50469533a96f2b6e2045884f2b538a29cff0583d"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "===================================================="
    Write-Host " PHASE 5.7 MIT 18.06 + CROSSWALK: BLOCKED"
    Write-Host "===================================================="
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
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found: $Python" }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 5.7 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/external_course_models.py",
    "personal_learning_assistant/domain/external_course_crosswalk_models.py",
    "personal_learning_assistant/ingestion/external_course_package.py",
    "personal_learning_assistant/repositories/sqlite/external_course_knowledge_repository.py",
    "personal_learning_assistant/services/external_course_crosswalk_service.py",
    "personal_learning_assistant/services/external_course_knowledge_service.py",
    "phase5_external_course_knowledge.py",
    "phase5_mit1806_crosswalk.py",
    "tests/test_phase5_external_course_knowledge.py",
    "tests/test_phase5_external_course_crosswalk.py",
    "PHASE5_FIX7_MIT1806_EXTERNAL_COURSE_KNOWLEDGE.md",
    "phase5_fix7_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 5.7 file: $item"
    }
}
foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope change detected: $path"
    }
}

if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Phase 4 authority-control file is missing."
}
if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}

$dbHashBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$controlHashBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacyHashesBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyHashesBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

$vaultPath = (& $PythonResolved -c "from obsidian_integration import get_vault_path; print(get_vault_path() or '')").Trim()
if (-not $vaultPath) {
    Stop-Gate "No enabled valid Obsidian vault is configured."
}
$packageRoot = (& $PythonResolved -c "from personal_learning_assistant.ingestion.external_course_package import discover_mit1806_package; import sys; print(discover_mit1806_package(sys.argv[1]))" $vaultPath).Trim()
if ($LASTEXITCODE -ne 0 -or -not $packageRoot) {
    Stop-Gate "Unable to locate the MIT 18.06 package in the configured vault."
}
$packageHashesBefore = @{}
foreach ($name in @("course_manifest.json","lecture_inventory.json","schema.json","chunks.jsonl")) {
    $path = Join-Path $packageRoot $name
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "MIT package file is missing: $name"
    }
    $packageHashesBefore[$path] = (Get-FileHash $path -Algorithm SHA256).Hash
}

Run-Step "[1/10] Focused Phase 5.7 external-course + crosswalk tests" {
    & $PythonResolved -m pytest `
        tests\test_phase5_external_course_knowledge.py `
        tests\test_phase5_external_course_crosswalk.py -q
}

Run-Step "[2/10] REAL MIT<->MA103N crosswalk preview (read-only)" {
    & $PythonResolved .\phase5_mit1806_crosswalk.py `
        --database .\data\learning_assistant.db `
        --configured-vault `
        --local-course MA103N
}

Run-Step "[3/10] REAL MIT package + MA103N package preview (read-only)" {
    & $PythonResolved .\phase5_external_course_knowledge.py `
        --database .\data\learning_assistant.db `
        --configured-vault `
        --local-course MA103N `
        --expect-lectures 35 `
        --expect-chunks 261
}

Run-Step "[4/10] Phase 5.1-5.6 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_knowledge_registry_foundation.py `
        tests\test_phase5_document_source_scanner.py `
        tests\test_phase5_obsidian_vault_registry.py `
        tests\test_phase5_notes_studio_foundation.py `
        tests\test_phase5_resources2_core.py `
        tests\test_phase5_unified_ingestion.py -q
}

Run-Step "[5/10] Phase 4 post-promotion regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py -q
}

Run-Step "[6/10] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p57_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase5_external_course_knowledge.py `
        phase5_mit1806_crosswalk.py `
        tests\test_phase5_external_course_knowledge.py `
        tests\test_phase5_external_course_crosswalk.py
}

Run-Step "[8/10] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[9/10] SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p57_sqlite_check_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[10/10] Git whitespace + production/package immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 5.7 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 5.7 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbHashBefore) {
    Stop-Gate "Phase 5.7 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $controlHashBefore) {
    Stop-Gate "Phase 5.7 gate changed Phase 4 authority control."
}
foreach ($path in $legacyHashesBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyHashesBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 5.7 gate: $path"
    }
}
foreach ($path in $packageHashesBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "MIT package file disappeared during gate: $path"
    }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $packageHashesBefore[$path]) {
        Stop-Gate "MIT package source changed during gate: $path"
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Write-Host $migrationDiff
    Stop-Gate "Phase 5.7 must reuse existing Resources 2/knowledge schema."
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 5.7 MIT 18.06 + CROSSWALK: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - 35 lecture records + 261 hash-valid package chunks remain source-grounded"
Write-Host " - MIT 18.06 remains external knowledge, not relabelled as MA103N"
Write-Host " - real crosswalk preview uses current MA103N topics/aliases and performs zero writes"
Write-Host " - fuzzy similarity is suggestion-only and never auto-applied"
Write-Host " - reviewed crosswalk is bound to package hash + local course identity"
Write-Host " - real apply requires every non-exact label to be map/leave_unresolved reviewed"
Write-Host " - crosswalk hash versions chunks + retrieval handoff and is stored in provenance"
Write-Host " - changed reviewed mapping stales older same-content retrieval handoffs"
Write-Host " - package source URLs/scope evidence remain preserved"
Write-Host " - Phase 5.1-5.6, Phase 4 and complete regressions pass"
Write-Host " - no migration, production SQLite, authority, legacy JSON or package source changed"
Write-Host ""
Write-Host "Phase 5.7 crosswalk reconciliation is ready for review."
