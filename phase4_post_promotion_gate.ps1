param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [Parameter(Mandatory=$true)]
    [string]$BackupDir
)

$ErrorActionPreference = "Stop"
$BaseCommit = "b6bb37ebbacc613f795c8c2df792e89218bd2906"
$ExpectedBranch = "phase4/structured-cutover"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=========================================================="
    Write-Host " PHASE 4 POST-PROMOTION VERIFICATION/CLOSURE: BLOCKED"
    Write-Host "=========================================================="
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
    $PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $PythonCommand) { Stop-Gate "Python interpreter was not found: $Python" }
    $PythonResolved = $PythonCommand.Source
}

$allowedChanges = @(
    ".gitignore",
    "personal_learning_assistant/migration/post_promotion_verification.py",
    "phase4_verify_sqlite_closure.py",
    "tests/test_phase4_post_promotion_verification.py",
    "PHASE4_POST_PROMOTION_VERIFICATION_CLOSURE.md",
    "phase4_post_promotion_gate.ps1"
)

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current branch." }
if ($currentBranch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $currentBranch."
}
$currentHead = (git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to read current HEAD." }
if ($currentHead -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted closure work on $BaseCommit but found $currentHead."
}

foreach ($path in $allowedChanges) {
    if (-not (Test-Path $path -PathType Leaf)) {
        Stop-Gate "Required closure file is missing: $path"
    }
}

$allowedSet = @{}
foreach ($path in $allowedChanges) { $allowedSet[$path] = $true }
$statusLines = @(git status --porcelain=v1 -uall)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect repository status." }
foreach ($line in $statusLines) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim()
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    $path = $path.Replace("\", "/")
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope tracked/untracked source change detected: $path"
    }
}

if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) {
    Stop-Gate "SQLite authority-control file is missing."
}
if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Authoritative SQLite database is missing."
}
if (Test-Path ".\.phase4_cutover.lock") {
    Stop-Gate "Cutover lock still exists after promotion."
}
if (Test-Path ".\.phase4_cutover_work") {
    Stop-Gate "Cutover work directory still exists after promotion."
}
if (-not (Test-Path $BackupDir -PathType Container)) {
    Stop-Gate "Final promotion backup directory does not exist: $BackupDir"
}

$ignoredControl = git check-ignore ".phase4_authority.json"
if ($LASTEXITCODE -ne 0) {
    Stop-Gate ".phase4_authority.json is not ignored by Git."
}
$ignoredDb = git check-ignore "data/learning_assistant.db"
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "data/learning_assistant.db is not ignored by Git."
}

$trackedRuntime = @(
    git ls-files -- ".phase4_authority.json" ".phase4_cutover.lock" ".phase4_cutover_work" "data/learning_assistant.db" "data/learning_assistant.db-wal" "data/learning_assistant.db-shm"
)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked runtime state." }
if ($trackedRuntime.Count -ne 0) {
    Write-Host $trackedRuntime
    Stop-Gate "Runtime authority/database artifacts must remain untracked."
}

Run-Step "[1/9] Focused post-promotion closure tests" {
    & $PythonResolved -m pytest tests\test_phase4_post_promotion_verification.py -q
}

Run-Step "[2/9] REAL runtime read-only post-promotion verification" {
    & $PythonResolved .\phase4_verify_sqlite_closure.py --project-root . --backup-dir $BackupDir
}

Run-Step "[3/9] Phase 4.11 structured authority routing regression" {
    & $PythonResolved -m pytest tests\test_phase4_structured_authority_routing.py -q
}

Run-Step "[4/9] Phase 4.10 SQLite command/legacy guard regression" {
    & $PythonResolved -m pytest tests\test_phase4_sqlite_command_repositories.py -q
}

Run-Step "[5/9] Final locked promotion + Phase 4.9 authority safety regressions" {
    & $PythonResolved -m pytest tests\test_phase4_final_locked_promotion.py tests\test_phase4_authority_promotion.py -q
}

Run-Step "[6/9] Final Phase 4 reconciliation regression" {
    & $PythonResolved -m pytest tests\test_phase4_final_reconciliation.py -q
}

Run-Step "[7/9] Python compilation" {
    & $PythonResolved -m compileall -q .
}

Run-Step "[8/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Write-Host ""
Write-Host "[9/9] Git whitespace + post-promotion runtime hygiene"
$stagedBefore = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect staged changes." }
if ($stagedBefore.Count -ne 0) {
    Write-Host $stagedBefore
    Stop-Gate "Closure gate expects no pre-staged changes."
}
$intentFailed = $false
$diffFailed = $false
try {
    git add --intent-to-add -- $allowedChanges
    if ($LASTEXITCODE -ne 0) { $intentFailed = $true }
    else {
        git diff --check $BaseCommit --
        if ($LASTEXITCODE -ne 0) { $diffFailed = $true }
    }
}
finally {
    git reset --quiet -- $allowedChanges 2>$null
}
if ($intentFailed) { Stop-Gate "Unable to mark closure files intent-to-add." }
if ($diffFailed) { Stop-Gate "git diff --check found whitespace/errors." }

$trackedPrivateJson = @(git ls-files -- "data/*.json" "data/**/*.json")
if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to inspect tracked private JSON." }
if ($trackedPrivateJson.Count -ne 0) {
    Write-Host $trackedPrivateJson
    Stop-Gate "Private legacy JSON must remain untracked."
}

if (Test-Path ".\.phase4_cutover.lock") { Stop-Gate "Closure verification created a cutover lock." }
if (Test-Path ".\.phase4_cutover_work") { Stop-Gate "Closure verification created a cutover work directory." }

Write-Host ""
Write-Host "=========================================================="
Write-Host " PHASE 4 POST-PROMOTION VERIFICATION/CLOSURE: PASS"
Write-Host "=========================================================="
Write-Host "Verified:"
Write-Host " - SQLite remains authoritative and legacy structured writes remain blocked"
Write-Host " - real promoted SQLite passes integrity/FK/migration checks"
Write-Host " - all nine compatibility projections exist and route through SQLite"
Write-Host " - legacy structured source manifest still matches promotion evidence"
Write-Host " - final backup manifest/artifact hashes and promotion evidence verify"
Write-Host " - closure verification performs reads only"
Write-Host " - unresolved study-plan topic evidence is reported, never guessed/repaired"
Write-Host " - authority/database/lock/work runtime artifacts remain untracked/ignored"
Write-Host " - Phase 4.9-4.11/final-promotion/final-reconciliation regressions pass"
Write-Host ""
Write-Host "Phase 4 is ready to be closed and committed."
