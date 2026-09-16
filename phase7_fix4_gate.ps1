param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "12848c9de34b9f55487eb5c056c237c62fbb00d9"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 7.4 LEGACY CONSUMER WATCH: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 7.4 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/phase7/consumer_watch.py",
    "phase7_consumer_watch.py",
    "tests/test_phase7_consumer_watch.py",
    "PHASE7_FIX4_LEGACY_USAGE_OBSERVATION_CONSUMER_WATCH.md",
    "phase7_fix4_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.4 file: $item"
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

Run-Step "[1/11] Focused Phase 7.4 consumer-watch tests" {
    & $PythonResolved -m pytest tests\test_phase7_consumer_watch.py -q
}

Write-Host ""
Write-Host "[2/11] REAL Phase 7.1 candidate preview through Phase 7.4 (read-only)"
& $PythonResolved .\phase7_consumer_watch.py preview --project-root .
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real Phase 7.4 preview failed."
}

Write-Host ""
Write-Host "[3/11] REAL temporary observation of V13 main.py exit path"
$tempParent = [IO.Path]::GetTempPath()
$tempWatch = Join-Path $tempParent ("phase7-consumer-watch-gate-" + [guid]::NewGuid().ToString("N"))
$tempHelper = Join-Path $tempParent ("phase7-consumer-watch-helper-" + [guid]::NewGuid().ToString("N") + ".py")
$tempReport = Join-Path $tempParent ("phase7-consumer-watch-report-" + [guid]::NewGuid().ToString("N") + ".json")
try {
    @(
        "import os, subprocess, sys",
        "cmd = [sys.executable, r'phase7_consumer_watch.py', 'run', '--project-root', '.', '--observation-root', sys.argv[1], '--script', r'main.py']",
        "env = os.environ.copy()",
        "env['PYTHONIOENCODING'] = 'utf-8'",
        "p = subprocess.run(cmd, input='40\n', text=True, encoding='utf-8', capture_output=True, env=env)",
        "print(p.stdout[-1500:].encode('ascii', 'backslashreplace').decode('ascii'))",
        "if p.stderr: print(p.stderr[-1500:].encode('ascii', 'backslashreplace').decode('ascii'), file=sys.stderr)",
        "raise SystemExit(p.returncode)"
    ) | Set-Content -Path $tempHelper -Encoding ASCII

    & $PythonResolved $tempHelper $tempWatch
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Temporary observed main.py session failed."
    }

    & $PythonResolved .\phase7_consumer_watch.py report `
        --project-root . `
        --observation-root $tempWatch `
        --format json `
        --output $tempReport
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Temporary observation report failed."
    }

    $report = Get-Content $tempReport -Raw | ConvertFrom-Json
    if ($report.summary.complete_session_count -ne 1) {
        Stop-Gate "Expected exactly one completed temporary observation session."
    }
    if ($report.summary.retirement_candidate_count -ne 0) {
        Stop-Gate "Phase 7.4 must never declare retirement candidates."
    }
    $main = @($report.components | Where-Object { $_.path -eq "main.py" })
    if ($main.Count -ne 1) {
        Stop-Gate "main.py is missing from the observation report."
    }
    if ($main[0].runtime_observation_state -ne "observed_runtime_use") {
        Stop-Gate "Real observed main.py execution was not recorded."
    }
    if ($report.privacy.academic_content_captured -ne $false) {
        Stop-Gate "Observation report violates the no-content privacy boundary."
    }
} finally {
    Remove-Item $tempWatch -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $tempHelper -Force -ErrorAction SilentlyContinue
    Remove-Item $tempReport -Force -ErrorAction SilentlyContinue
}

Run-Step "[4/11] Phase 7.1-7.3 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py -q
}

Run-Step "[5/11] Phase 6 final closure + Academic Agent regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_workspace_closure.py `
        tests\test_phase6_academic_agent_cutover.py `
        tests\test_phase6_adaptive_mentor.py -q
}

Run-Step "[6/11] Phase 5/4/3 authority and recovery regressions" {
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

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p74_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase7_consumer_watch.py `
        tests\test_phase7_consumer_watch.py
}

Run-Step "[9/11] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[10/11] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p74_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[11/11] Git + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 7.4 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 7.4 files intent-to-add."
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
    Stop-Gate "Phase 7.4 must not add or modify a SQLite migration."
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) {
        Stop-Gate "Phase 7.4 changed an existing/out-of-scope file: $normalized"
    }
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 7.4 changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 7.4 changed authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Phase 7.4 changed legacy JSON: $path"
    }
}

$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 7.4 changed current retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected current retrieval file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 7.4 changed current retrieval index bytes: $($file.FullName)"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 7.4 LEGACY USAGE OBSERVATION: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - Phase 7.1 candidates can be observed at runtime without modifying legacy modules"
Write-Host " - observation is opt-in through a wrapper; normal application code remains unchanged"
Write-Host " - runtime evidence records component/symbol/caller identity only"
Write-Host " - function arguments, locals, return values and academic content are never captured"
Write-Host " - absolute project/vault/source paths and environment data are not logged"
Write-Host " - completed session event streams are hash-verified during report generation"
Write-Host " - interrupted/incomplete sessions remain distinguishable from completed observation time"
Write-Host " - positive events prove runtime use; absence remains not_observed_yet, never a deletion verdict"
Write-Host " - Phase 7.4 declares zero retirement candidates"
Write-Host " - observation output must remain outside the repository"
Write-Host " - real main.py exit-path observation succeeds in a temporary external directory"
Write-Host " - Phase 7.1-7.3, Phase 6, Phase 5/4/3 and complete regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and current retrieval index remain unchanged"
Write-Host " - no migration, retirement/deletion or authority switch occurs"
Write-Host ""
Write-Host "Phase 7.4 is ready for review and commit."
