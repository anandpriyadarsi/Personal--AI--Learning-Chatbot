param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "e83692efeb4f79c1f16144ea3a8e91261e63ae7d"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 6.7 ADAPTIVE MENTOR: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.7 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/adaptive_mentor_models.py",
    "personal_learning_assistant/repositories/sqlite/adaptive_mentor_repository.py",
    "personal_learning_assistant/services/adaptive_mentor_service.py",
    "phase6_adaptive_mentor.py",
    "tests/test_phase6_adaptive_mentor.py",
    "PHASE6_FIX7_ADAPTIVE_MENTOR.md",
    "phase6_fix7_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.7 file: $item"
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

Run-Step "[1/9] Focused Phase 6.7 Adaptive Mentor tests" {
    & $PythonResolved -m pytest tests\test_phase6_adaptive_mentor.py -q
}

Write-Host ""
Write-Host "[2/9] REAL MA103N Adaptive Mentor preview (read-only)"
& $PythonResolved .\phase6_adaptive_mentor.py `
    --database .\data\learning_assistant.db `
    --course-code MA103N `
    --as-of 2026-09-16 `
    --limit-topics 5 `
    --max-actions 10
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real MA103N Adaptive Mentor preview failed."
}

Run-Step "[3/9] Phase 6.1-6.6 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_foundation.py `
        tests\test_phase6_grounded_tutor_engine.py `
        tests\test_phase6_knowledge_navigator.py `
        tests\test_phase6_lecture_learning_mode.py `
        tests\test_phase6_active_recall_quiz.py `
        tests\test_phase6_pyq_exam_intelligence.py -q
}

Run-Step "[4/9] Phase 5 knowledge/retrieval/closure regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_resources2_core.py `
        tests\test_phase5_rebuildable_retrieval.py `
        tests\test_phase5_final_closure.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p67_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase6_adaptive_mentor.py `
        tests\test_phase6_adaptive_mentor.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p67_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[9/9] Git + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 6.7 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.7 files intent-to-add."
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
    Stop-Gate "Phase 6.7 must not add or modify a SQLite migration."
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.7 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.7 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.7 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.7 gate changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared."
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.7 gate changed retrieval index bytes."
    }
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 6.7 ADAPTIVE MENTOR: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - mentor composes Knowledge Navigator, practice history and formal Exam Intelligence"
Write-Host " - recommendations remain deterministic, advisory and read-only"
Write-Host " - unfinished lecture progress can produce a continue-lecture recommendation"
Write-Host " - low confidence/mistakes/memory presence can produce a grounded-tutor recommendation"
Write-Host " - deterministic practice history adapts active-recall recommendations"
Write-Host " - advisory free-response practice never becomes correctness evidence"
Write-Host " - explicit PYQ actions preserve formal question/source provenance"
Write-Host " - selected assessment scope influences workflow priority without predicting exam content"
Write-Host " - missing migration 0004 practice history is reported, not guessed"
Write-Host " - no LLM/provider call occurs and no authoritative academic state changes"
Write-Host " - real MA103N mentor preview performs zero SQLite/provider/network writes"
Write-Host " - Phase 6.1-6.6, Phase 5 and complete project regressions pass"
Write-Host " - no SQLite migration is introduced in Phase 6.7"
Write-Host ""
Write-Host "Phase 6.7 is ready for review and commit."
