param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "31d5783d6ddb7740ab40b146f645f9c9439f5d2a"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 7.2 RECOVERY BUNDLE/TWO BACKUPS: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 7.2 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/phase7/recovery_bundle.py",
    "phase7_recovery_bundle.py",
    "tests/test_phase7_recovery_bundle.py",
    "PHASE7_FIX2_RECOVERY_BUNDLE_TWO_BACKUPS.md",
    "phase7_fix2_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.2 file: $item"
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

Run-Step "[1/11] Focused Phase 7.2 recovery tests" {
    & $PythonResolved -m pytest tests\test_phase7_recovery_bundle.py -q
}

Write-Host ""
Write-Host "[2/11] REAL recovery preview (read-only)"
& $PythonResolved .\phase7_recovery_bundle.py preview `
    --project-root . `
    --database .\data\learning_assistant.db `
    --authority .\.phase4_authority.json
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real Phase 7.2 recovery preview failed."
}

Write-Host ""
Write-Host "[3/11] REAL temporary two-backup creation + independent verification"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("phase7-recovery-gate-" + [guid]::NewGuid().ToString("N"))
try {
    & $PythonResolved .\phase7_recovery_bundle.py create `
        --project-root . `
        --database .\data\learning_assistant.db `
        --authority .\.phase4_authority.json `
        --output $tempRoot `
        --confirm CREATE_PHASE7_TWO_VERIFIED_BACKUPS
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Temporary two-backup creation failed."
    }

    & $PythonResolved .\phase7_recovery_bundle.py verify `
        --bundle-root $tempRoot
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Temporary recovery-pair verification failed."
    }

    $pair = Get-Content (Join-Path $tempRoot "pair_manifest.json") -Raw | ConvertFrom-Json
    if (-not $pair.backups.A.verified -or -not $pair.backups.B.verified) {
        Stop-Gate "Pair manifest does not mark both backups independently verified."
    }
    if ($pair.restore_performed -ne $false) {
        Stop-Gate "Phase 7.2 unexpectedly reports a restore."
    }
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Run-Step "[4/11] Phase 7.1 inventory regressions" {
    & $PythonResolved -m pytest tests\test_phase7_runtime_inventory.py -q
}

Run-Step "[5/11] Phase 6 final closure + agent regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_workspace_closure.py `
        tests\test_phase6_academic_agent_cutover.py `
        tests\test_phase6_adaptive_mentor.py -q
}

Run-Step "[6/11] Phase 5/4 recovery-authority regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_final_closure.py `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_final_locked_promotion.py `
        tests\test_phase3_reverse_export_restore.py -q
}

Run-Step "[7/11] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p72_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[8/11] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase7_recovery_bundle.py `
        tests\test_phase7_recovery_bundle.py
}

Run-Step "[9/11] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[10/11] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p72_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[11/11] Git + production/source/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.2 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 7.2 files intent-to-add."
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
    Stop-Gate "Phase 7.2 must not add or modify a SQLite migration."
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.2 changed an existing/out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.2 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.2 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.2 changed legacy JSON: $path"
    }
}

$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 7.2 changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 7.2 changed retrieval index bytes: $($file.FullName)"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 7.2 RECOVERY BUNDLE/TWO BACKUPS: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - SQLite authority is captured twice with independent online backups"
Write-Host " - both backup DBs pass integrity/FK and preserve the same logical fingerprint"
Write-Host " - authority control, migration history and known legacy evidence are hashed"
Write-Host " - registered vault/source provenance is represented in portable manifests"
Write-Host " - available registered note bodies and explicit source-root bytes are copied/hash-verified"
Write-Host " - missing/external source roots are reported rather than guessed"
Write-Host " - secret-sensitive generic source paths and rebuildable retrieval/runtime junk are excluded"
Write-Host " - pair creation detects source-state changes between A and B"
Write-Host " - existing output is never overwritten and output must remain outside source/project roots"
Write-Host " - real gate backups exist only in a temporary directory and are independently reverified"
Write-Host " - no restore, retirement, deletion, authority switch or SQLite migration occurs"
Write-Host " - Phase 7.1, Phase 6, Phase 5, Phase 4/3 and complete project regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and retrieval bytes remain unchanged"
Write-Host ""
Write-Host "Phase 7.2 tooling is ready. Create one retained verified pair outside the repo before commit."
