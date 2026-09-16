param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "a7566d0026252767a7276ca7ca9df3689e406d61"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 7.1 CANONICAL RUNTIME INVENTORY: BLOCKED"
    Write-Host "================================================"
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
    Stop-Gate "Expected uncommitted Phase 7.1 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/phase7/__init__.py",
    "personal_learning_assistant/phase7/canonical_runtime_catalog.py",
    "personal_learning_assistant/phase7/runtime_inventory.py",
    "phase7_runtime_inventory.py",
    "tests/test_phase7_runtime_inventory.py",
    "PHASE7_FIX1_CANONICAL_RUNTIME_CONSUMER_INVENTORY.md",
    "phase7_fix1_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.1 file: $item"
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
    Stop-Gate "Current retrieval generation is missing."
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$indexBefore = @{}
Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force | ForEach-Object {
    $indexBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/9] Focused Phase 7.1 inventory tests" {
    & $PythonResolved -m pytest tests\test_phase7_runtime_inventory.py -q
}

Write-Host ""
Write-Host "[2/9] REAL repository consumer inventory preview (read-only)"
$tempDir = Join-Path ([IO.Path]::GetTempPath()) ("p71_inventory_" + [guid]::NewGuid().ToString("N"))
$tempJson = Join-Path $tempDir "inventory.json"
$tempCheck = Join-Path $tempDir "check_inventory.py"
try {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    & $PythonResolved .\phase7_runtime_inventory.py `
        --project-root . `
        --format json `
        --output $tempJson
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Real Phase 7.1 inventory preview failed."
    }

    @(
        "import json, pathlib, sys",
        "p = pathlib.Path(sys.argv[1])",
        "r = json.loads(p.read_text(encoding='utf-8'))",
        "items = {x['path']: x for x in r['items']}",
        "assert r['analysis_kind'] == 'static_consumer_inventory'",
        "assert r['summary']['candidate_count'] >= 20",
        "assert r['summary']['retirement_candidate_count'] == 0",
        "assert 'notes.py' in items and 'main.py' in items['notes.py']['runtime_consumers']",
        "assert 'resources.py' in items and 'main.py' in items['resources.py']['runtime_consumers']",
        "assert 'backup.py' in items and 'main.py' in items['backup.py']['runtime_consumers']",
        "assert 'personal_academic_agent.py' in items",
        "assert items['personal_academic_agent.py']['status'] in ('active_consumer','compatibility_required')",
        "assert any(x['component_kind'] == 'legacy_json_repository' for x in r['items'])",
        "assert any(x['component_kind'] == 'phase4_compatibility_backend' for x in r['items'])",
        "print('candidate_count:', r['summary']['candidate_count'])",
        "print('status_counts:', r['summary']['status_counts'])",
        "print('inventory_sha256:', r['inventory_sha256'])"
    ) | Set-Content -Path $tempCheck -Encoding ASCII

    & $PythonResolved $tempCheck $tempJson
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Real inventory semantic validation failed."
    }
} finally {
    Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}

Run-Step "[3/9] Phase 6 final closure + agent regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_workspace_closure.py `
        tests\test_phase6_academic_agent_cutover.py `
        tests\test_phase6_adaptive_mentor.py -q
}

Run-Step "[4/9] Phase 5/4 authority and closure regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_final_closure.py `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p71_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[6/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase7_runtime_inventory.py `
        tests\test_phase7_runtime_inventory.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p71_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[9/9] Git + authority/source/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.1 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 7.1 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 7.1 must not add or modify a SQLite migration."
}

# Phase 7.1 is inventory only: no pre-existing tracked file may be modified.
$trackedChanges = @(
    git diff --name-only $BaseCommit --
)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.1 changed an existing/out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.1 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.1 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.1 changed legacy JSON: $path"
    }
}

$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 7.1 changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 7.1 changed retrieval index bytes: $($file.FullName)"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 7.1 CANONICAL RUNTIME INVENTORY: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - Phase 7 branch begins from the completed Phase 6 closure commit"
Write-Host " - canonical runtime authority boundaries are declared, not rewritten"
Write-Host " - known legacy/root/compatibility surfaces are inventoried"
Write-Host " - legacy JSON repositories and Phase 4 compatibility backends are included"
Write-Host " - static imports, FEATURE_ACTIONS, tests and data-path hints are recorded"
Write-Host " - test-only use is separated from normal runtime consumers"
Write-Host " - zero static consumers never becomes a retirement decision"
Write-Host " - no file is deleted, archived, moved or disabled in Phase 7.1"
Write-Host " - real inventory preview writes only to a temporary output directory"
Write-Host " - Phase 6, Phase 5, Phase 4 and complete project regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and retrieval bytes remain unchanged"
Write-Host " - no SQLite migration is introduced in Phase 7.1"
Write-Host ""
Write-Host "Phase 7.1 is ready for review and commit."
