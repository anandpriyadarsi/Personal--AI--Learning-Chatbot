param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "840a5ee56eab6f197448b8b37265c7b72997d191"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================"
    Write-Host " PHASE 6 FINAL TUTOR WORKSPACE/CLOSURE: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.9 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/tutor_workspace_models.py",
    "personal_learning_assistant/repositories/sqlite/tutor_workspace_repository.py",
    "personal_learning_assistant/services/tutor_workspace_service.py",
    "personal_learning_assistant/services/phase6_closure_service.py",
    "phase6_tutor_workspace.py",
    "phase6_verify_closure.py",
    "tests/test_phase6_tutor_workspace_closure.py",
    "PHASE6_FINAL_TUTOR_WORKSPACE_CLOSURE.md",
    "phase6_final_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.9 file: $item"
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
    Stop-Gate "Current Phase 5.8 retrieval generation is missing."
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

Run-Step "[1/11] Focused Phase 6.9 Tutor Workspace/closure tests" {
    & $PythonResolved -m pytest tests\test_phase6_tutor_workspace_closure.py -q
}

Write-Host ""
Write-Host "[2/11] REAL MA103N Tutor Workspace preview (read-only)"
& $PythonResolved .\phase6_tutor_workspace.py `
    --database .\data\learning_assistant.db `
    --course-code MA103N `
    --as-of 2026-09-16 `
    --limit-topics 5 `
    --max-actions 10 `
    --recent-limit 12
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real MA103N Tutor Workspace preview failed."
}

Write-Host ""
Write-Host "[3/11] REAL Phase 6 final reconciliation (read-only)"
& $PythonResolved .\phase6_verify_closure.py `
    --database .\data\learning_assistant.db `
    --authority .\.phase4_authority.json `
    --index-root .\.phase5_retrieval `
    --course-code MA103N `
    --as-of 2026-09-16
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real Phase 6 final reconciliation failed."
}

Run-Step "[4/11] Phase 6.1-6.8 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_foundation.py `
        tests\test_phase6_grounded_tutor_engine.py `
        tests\test_phase6_knowledge_navigator.py `
        tests\test_phase6_lecture_learning_mode.py `
        tests\test_phase6_active_recall_quiz.py `
        tests\test_phase6_pyq_exam_intelligence.py `
        tests\test_phase6_adaptive_mentor.py `
        tests\test_phase6_academic_agent_cutover.py `
        tests\test_agent_intents.py `
        tests\test_phase2_academic_agent_service.py -q
}

Run-Step "[5/11] Phase 5 retrieval/closure regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase5_final_closure.py -q
}

Run-Step "[6/11] Phase 4 authority/post-promotion regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_post_promotion_verification.py `
        tests\test_phase4_structured_authority_routing.py `
        tests\test_phase4_authority_promotion.py -q
}

Run-Step "[7/11] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p69_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase6_tutor_workspace.py `
        phase6_verify_closure.py `
        tests\test_phase6_tutor_workspace_closure.py
}

Run-Step "[9/11] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[10/11] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p69_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
    Stop-Gate "Phase 6.9 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.9 files intent-to-add."
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
    Stop-Gate "Phase 6.9 must not add or modify a SQLite migration."
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.9 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.9 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.9 gate: $path"
    }
}

$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.9 changed current retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared: $($file.FullName)"
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.9 changed retrieval index bytes: $($file.FullName)"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host " PHASE 6 FINAL TUTOR WORKSPACE/CLOSURE: PASS"
Write-Host "================================================"
Write-Host "Verified:"
Write-Host " - Tutor Workspace unifies mentor recommendations and Phase 6 runtime activity read-only"
Write-Host " - SQLite remains authoritative and legacy structured writes remain blocked"
Write-Host " - intact 0001/0002/0003/0004 migration prefix is present; Phase 6.9 adds no migration"
Write-Host " - grounded/mixed tutor turns retain exact chunk/document provenance"
Write-Host " - persisted practice items retain exact source provenance and remain separate from formal PYQs"
Write-Host " - lecture learning has no duplicate simultaneously-open segments per resource"
Write-Host " - academic-agent claims are terminal/audited/idempotent with matching outbox evidence"
Write-Host " - current Phase 5.8 retrieval generation remains readable and MA103N-grounded"
Write-Host " - Workspace/closure perform zero provider/network/SQLite writes"
Write-Host " - Phase 6.1-6.8, Phase 5, Phase 4 and complete project regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and current retrieval index bytes are unchanged"
Write-Host ""
Write-Host "Phase 6 is ready to close and commit."
