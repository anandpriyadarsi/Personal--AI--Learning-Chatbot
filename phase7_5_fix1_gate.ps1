param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "0a949a028a6152d43d7ba1fd33220b8bcd054799"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================="
    Write-Host " PHASE 7.5.1 WEB FOUNDATION: BLOCKED"
    Write-Host "============================================="
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
    Stop-Gate "Expected uncommitted Phase 7.5.1 work on $BaseCommit but found $head."
}

$allowed = @(
    "requirements.txt",
    "personal_learning_assistant/ui/web/__init__.py",
    "personal_learning_assistant/ui/web/__main__.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/errors.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/home.html",
    "personal_learning_assistant/ui/web/templates/errors/404.html",
    "personal_learning_assistant/ui/web/templates/errors/500.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "phase7_web.py",
    "tests/test_phase7_5_web_foundation.py",
    "PHASE7_5_FIX1_WEB_FOUNDATION.md",
    "phase7_5_fix1_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }

foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}

foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.5.1 file: $item"
    }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "Phase 4 authority-control file is missing."
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/9] Focused Phase 7.5.1 web tests" {
    & $PythonResolved -m pytest tests\test_phase7_5_web_foundation.py -q
}

Run-Step "[2/9] Web startup and health smoke test" {
    & $PythonResolved -c "from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING': True}).test_client(); r=c.get('/healthz'); assert r.status_code == 200; assert r.get_json()['status'] == 'ok'"
}

Run-Step "[3/9] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py `
        tests\test_phase7_consumer_watch.py -q
}

Run-Step "[4/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p751_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[5/9] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\ui\web `
        phase7_web.py `
        tests\test_phase7_5_web_foundation.py
}

Run-Step "[6/9] Flask runtime dependency + pip consistency" {
    & $PythonResolved -c "import importlib.metadata; import flask; from flask import Flask; assert Flask is not None; assert importlib.metadata.version('Flask') == '3.1.2'"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

Run-Step "[7/9] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p751_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[8/9] Scope + completed Phase 7 immutability"
$migrationDiff = @(git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 7.5.1 must not add or modify SQLite migrations."
}
$protected = @(
    "personal_learning_assistant/phase7",
    "phase7_runtime_inventory.py",
    "phase7_recovery_bundle.py",
    "phase7_restore_rehearsal.py",
    "phase7_consumer_watch.py",
    "phase7_fix1_gate.ps1",
    "phase7_fix2_gate.ps1",
    "phase7_fix3_gate.ps1",
    "phase7_fix4_gate.ps1",
    "PHASE7_FIX1_CANONICAL_RUNTIME_CONSUMER_INVENTORY.md",
    "PHASE7_FIX2_RECOVERY_BUNDLE_TWO_BACKUPS.md",
    "PHASE7_FIX3_FULL_RESTORE_REVERSE_RESTORE_REHEARSAL.md",
    "PHASE7_FIX4_LEGACY_USAGE_OBSERVATION_CONSUMER_WATCH.md"
)
$protectedDiff = @(git diff --name-only $BaseCommit -- $protected)
if ($protectedDiff.Count -ne 0) {
    Stop-Gate "Phase 7.5.1 changed completed Phase 7.1-7.4 files: $($protectedDiff -join ', ')"
}

Write-Host ""
Write-Host "[9/9] Git + production immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.5.1 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.1 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
} finally {
    git reset --quiet -- $allowed 2>$null
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.5.1 changed an out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.5.1 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.5.1 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.5.1 changed legacy JSON: $path"
    }
}

Write-Host ""
Write-Host "============================================="
Write-Host " PHASE 7.5.1 WEB FOUNDATION: PASS"
Write-Host "============================================="
Write-Host "Verified:"
Write-Host " - local-only Flask application factory"
Write-Host " - read-only Home and health routes"
Write-Host " - local Jinja/CSS application shell"
Write-Host " - optional AI and legacy CLI startup isolation"
Write-Host " - Phase 7.1-7.4 and complete regressions"
Write-Host " - production SQLite and authority remain unchanged"
Write-Host " - no migration, deprecation, deletion or authority switch occurs"
Write-Host ""
Write-Host "Phase 7.5.1 is ready for review and commit."
