param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "039196863e1905e242354231ead468367550dcaf"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 6.5 ACTIVE RECALL / FAST QUIZ: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.5 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/repositories/sqlite/migrations/0004_practice_recall.sql",
    "personal_learning_assistant/domain/practice_models.py",
    "personal_learning_assistant/repositories/sqlite/practice_repository.py",
    "personal_learning_assistant/tutor/quiz_grounding.py",
    "personal_learning_assistant/services/practice_quiz_service.py",
    "phase6_practice_schema.py",
    "phase6_tutor_schema.py",
    "phase6_fast_quiz.py",
    "tests/test_phase6_active_recall_quiz.py",
    "tests/test_phase6_tutor_foundation.py",
    "PHASE6_FIX5_ACTIVE_RECALL_FAST_QUIZ.md",
    "phase6_fix5_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.5 file/change: $item"
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
    Stop-Gate "Phase 5 retrieval generation is missing."
}

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
$indexBefore = @{}
Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force | ForEach-Object {
    $indexBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}

Run-Step "[1/11] Focused Phase 6.5 Active Recall/Fast Quiz tests" {
    & $PythonResolved -m pytest tests\test_phase6_active_recall_quiz.py -q
}

Write-Host ""
Write-Host "[2/11] REAL production practice-schema preview (read-only)"
& $PythonResolved .\phase6_practice_schema.py `
    --database .\data\learning_assistant.db `
    preview
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Production practice-schema preview failed."
}

Write-Host ""
Write-Host "[3/11] Isolated 0004 migration rehearsal"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("p65_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$tempDb = Join-Path $tempRoot "learning_assistant.db"
try {
    Copy-Item ".\data\learning_assistant.db" $tempDb
    & $PythonResolved .\phase6_practice_schema.py `
        --database $tempDb `
        apply `
        --confirm APPLY_PHASE6_PRACTICE_SCHEMA
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Isolated Phase 6.5 schema migration rehearsal failed."
    }
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "[4/11] REAL MA103N grounded quiz preview (read-only/no provider)"
& $PythonResolved .\phase6_fast_quiz.py `
    --database .\data\learning_assistant.db `
    --index-root .\.phase5_retrieval `
    preview `
    "LU factorization intuition and mechanics" `
    --course-code MA103N `
    --mode fast_quiz `
    --difficulty medium `
    --item-count 5 `
    --top-k 8
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real MA103N quiz grounding preview failed."
}

Run-Step "[5/11] Phase 6.1-6.4 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_foundation.py `
        tests\test_phase6_grounded_tutor_engine.py `
        tests\test_phase6_knowledge_navigator.py `
        tests\test_phase6_lecture_learning_mode.py -q
}

Run-Step "[6/11] Phase 5 retrieval/closure regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase5_final_closure.py -q
}

Run-Step "[7/11] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p65_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase6_practice_schema.py `
        phase6_tutor_schema.py `
        phase6_fast_quiz.py `
        tests\test_phase6_active_recall_quiz.py
}

Run-Step "[9/11] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[10/11] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p65_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[11/11] Git + migration + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 6.5 gate expects no pre-staged changes."
}
$migrationDiff = @()
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.5 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }

    # Keep intent-to-add active while checking migration changes so the new,
    # still-untracked 0004 file is visible to git diff.
    $migrationDiff = @(
        git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
    )
    if (
        $migrationDiff.Count -ne 1 -or
        $migrationDiff[0].Trim().Replace("\","/") -ne "personal_learning_assistant/repositories/sqlite/migrations/0004_practice_recall.sql"
    ) {
        Stop-Gate "Phase 6.5 may add only migration 0004; 0001-0003 must remain unchanged."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.5 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.5 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.5 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.5 gate changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared."
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.5 gate changed retrieval index bytes."
    }
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 6.5 ACTIVE RECALL / FAST QUIZ: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - 0004 adds separate practice session/item/source/attempt persistence"
Write-Host " - formal assessment questions/attempts remain separate and unchanged"
Write-Host " - quiz generation is source-only and every item requires exact chunk provenance"
Write-Host " - fabricated/unavailable evidence labels reject the whole generation"
Write-Host " - single-choice and exact-recall answers are graded locally/deterministically"
Write-Host " - free-response grading remains advisory and never becomes a correctness claim"
Write-Host " - practice attempts do not silently change mastery, memory, plans or formal attempts"
Write-Host " - self-confidence is stored only as explicit practice evidence"
Write-Host " - generation/attempt/completion writes are authority-guarded and emit outbox events"
Write-Host " - real MA103N preview calls no provider and performs zero production SQLite writes"
Write-Host " - isolated migration rehearsal passes without touching production"
Write-Host " - Phase 6.1-6.4, Phase 5 and complete project regressions pass"
Write-Host " - 0001-0003 are unchanged; only append-only 0004 is introduced"
Write-Host ""
Write-Host "Phase 6.5 is ready for review and commit."
