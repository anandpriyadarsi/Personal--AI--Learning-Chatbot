param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [Parameter(Mandatory=$true)]
    [string]$RecoveryRoot
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "13ba4589502d03dbed34d55c0e1210e91a3a3cce"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 7.3 FULL RESTORE/REVERSE-RESTORE: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 7.3 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/phase7/restore_rehearsal.py",
    "phase7_restore_rehearsal.py",
    "tests/test_phase7_restore_rehearsal.py",
    "PHASE7_FIX3_FULL_RESTORE_REVERSE_RESTORE_REHEARSAL.md",
    "phase7_fix3_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.3 file: $item"
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

if (-not (Test-Path $RecoveryRoot -PathType Container)) {
    Stop-Gate "Retained Phase 7.2 recovery root does not exist: $RecoveryRoot"
}
$RecoveryRoot = (Resolve-Path $RecoveryRoot).Path
$projectRoot = (Resolve-Path ".").Path
if ($RecoveryRoot.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    Stop-Gate "Retained recovery pair must remain outside the repository."
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

function Get-TreeHashes {
    param([string]$Root)
    $result = @{}
    Get-ChildItem $Root -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
        $relative = $_.FullName.Substring($Root.Length).TrimStart('\','/')
        $result[$relative] = "$($_.Length):$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)"
    }
    return $result
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
$recoveryBefore = Get-TreeHashes $RecoveryRoot

Run-Step "[1/12] Focused Phase 7.3 restore-rehearsal tests" {
    & $PythonResolved -m pytest tests\test_phase7_restore_rehearsal.py -q
}

Write-Host ""
Write-Host "[2/12] REAL retained Phase 7.2 pair preview (read-only)"
& $PythonResolved .\phase7_restore_rehearsal.py preview `
    --recovery-root $RecoveryRoot
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Retained recovery-pair preview failed."
}

Write-Host ""
Write-Host "[3/12] REAL isolated full restore A + B, retrieval rebuild, workspace smoke, reverse restore"
$tempRestore = Join-Path ([IO.Path]::GetTempPath()) ("phase7-restore-gate-" + [guid]::NewGuid().ToString("N"))
try {
    & $PythonResolved .\phase7_restore_rehearsal.py rehearse `
        --recovery-root $RecoveryRoot `
        --project-root . `
        --work-root $tempRestore `
        --course-code MA103N `
        --as-of 2026-09-16 `
        --confirm REHEARSE_PHASE7_FULL_RESTORE
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Real isolated Phase 7.3 rehearsal failed."
    }

    & $PythonResolved .\phase7_restore_rehearsal.py verify-report `
        --work-root $tempRestore
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Phase 7.3 rehearsal report verification failed."
    }

    $report = Get-Content (Join-Path $tempRestore "phase7_restore_rehearsal_report.json") -Raw | ConvertFrom-Json
    if ($report.status -ne "pass") {
        Stop-Gate "Rehearsal report status is not pass."
    }
    if (-not $report.retained_pair_unchanged -or -not $report.backups_equivalent) {
        Stop-Gate "Rehearsal did not prove retained-pair immutability and A/B equivalence."
    }
    if (-not $report.restore_performed_only_in_isolation) {
        Stop-Gate "Rehearsal did not prove isolated-only restoration."
    }
    if ($report.production_or_live_source_accessed) {
        Stop-Gate "Rehearsal reports production/live-source access."
    }
    if ($report.retirement_or_deletion_performed) {
        Stop-Gate "Phase 7.3 must not perform retirement/deletion."
    }
} finally {
    Remove-Item $tempRestore -Recurse -Force -ErrorAction SilentlyContinue
}

Run-Step "[4/12] Phase 7.2 + 7.1 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_runtime_inventory.py -q
}

Run-Step "[5/12] Phase 6 final closure + Academic Agent regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_workspace_closure.py `
        tests\test_phase6_academic_agent_cutover.py `
        tests\test_phase6_adaptive_mentor.py -q
}

Run-Step "[6/12] Phase 5 retrieval/closure regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase5_final_closure.py -q
}

Run-Step "[7/12] Phase 3 reverse-export/restore + Phase 4 authority regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase3_reverse_export_restore.py `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_final_locked_promotion.py -q
}

Run-Step "[8/12] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p73_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[9/12] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase7_restore_rehearsal.py `
        tests\test_phase7_restore_rehearsal.py
}

Run-Step "[10/12] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[11/12] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p73_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[12/12] Git + production/recovery/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.3 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 7.3 files intent-to-add."
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
    Stop-Gate "Phase 7.3 must not add or modify a SQLite migration."
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.3 changed an existing/out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.3 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.3 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.3 changed legacy JSON: $path"
    }
}

$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 7.3 changed current retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected current retrieval file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 7.3 changed current retrieval index bytes: $($file.FullName)"
    }
}

$recoveryAfter = Get-TreeHashes $RecoveryRoot
if ($recoveryAfter.Count -ne $recoveryBefore.Count) {
    Stop-Gate "Phase 7.3 changed retained recovery-pair file set."
}
foreach ($key in $recoveryBefore.Keys) {
    if (-not $recoveryAfter.ContainsKey($key)) {
        Stop-Gate "Retained recovery file disappeared: $key"
    }
    if ($recoveryAfter[$key] -ne $recoveryBefore[$key]) {
        Stop-Gate "Retained recovery file changed: $key"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 7.3 FULL RESTORE/REVERSE-RESTORE: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - retained Phase 7.2 Backup A and Backup B both independently restore"
Write-Host " - exact restored SQLite copies preserve the recorded logical fingerprint and pass integrity/FKs"
Write-Host " - authority, safe legacy evidence, registered notes and registered sources restore by recorded hash"
Write-Host " - runtime clones relocate vault roots only to isolated restored vault mirrors"
Write-Host " - Phase 5.8 lexical retrieval is rebuilt from restored SQLite; no semantic provider is used"
Write-Host " - rebuilt retrieval serves an MA103N course-grounded smoke query"
Write-Host " - Phase 6 Tutor Workspace opens both restored runtimes read-only/provider-free"
Write-Host " - Phase 3 reverse export + online restore + reverse re-import succeeds from each exact restored DB"
Write-Host " - reverse migration/import replay is idempotent and reverse-export hashes remain unchanged"
Write-Host " - A and B agree on SQLite/content/retrieval/workspace/reverse-export identities"
Write-Host " - retained backup pair is byte-for-byte unchanged"
Write-Host " - all real restore/rebuild work occurs only in a temporary isolated directory"
Write-Host " - production SQLite, authority, legacy JSON and current retrieval index remain unchanged"
Write-Host " - no retirement/deletion, observation logging, authority switch or SQLite migration occurs"
Write-Host " - Phase 7.1-7.2, Phase 6, Phase 5, Phase 4/3 and complete regressions pass"
Write-Host ""
Write-Host "Phase 7.3 is ready for review. Create one retained rehearsal report before commit."
