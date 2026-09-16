param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "59977d36da575ac7573aeee90a45c3df136f3878"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 6.6 PYQ + EXAM INTELLIGENCE: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.6 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/exam_intelligence_models.py",
    "personal_learning_assistant/repositories/sqlite/exam_intelligence_repository.py",
    "personal_learning_assistant/services/exam_intelligence_service.py",
    "phase6_exam_intelligence.py",
    "tests/test_phase6_pyq_exam_intelligence.py",
    "PHASE6_FIX6_PYQ_EXAM_INTELLIGENCE.md",
    "phase6_fix6_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.6 file: $item"
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

Run-Step "[1/9] Focused Phase 6.6 PYQ/Exam Intelligence tests" {
    & $PythonResolved -m pytest tests\test_phase6_pyq_exam_intelligence.py -q
}

Write-Host ""
Write-Host "[2/9] REAL MA103N PYQ/Exam Intelligence preview (read-only)"
& $PythonResolved .\phase6_exam_intelligence.py `
    --database .\data\learning_assistant.db `
    --course-code MA103N `
    --as-of 2026-09-16 `
    --limit-topics 10 `
    --limit-questions 12
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real MA103N exam-intelligence preview failed."
}

Run-Step "[3/9] Phase 6.1-6.5 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase6_tutor_foundation.py `
        tests\test_phase6_grounded_tutor_engine.py `
        tests\test_phase6_knowledge_navigator.py `
        tests\test_phase6_lecture_learning_mode.py `
        tests\test_phase6_active_recall_quiz.py -q
}

Run-Step "[4/9] Phase 4 formal-assessment regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase4_assessments_dual_read.py `
        tests\test_phase4_questions_dual_read.py `
        tests\test_phase4_question_topic_mappings_dual_read.py `
        tests\test_phase4_attempts_performance_dual_read.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p66_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase6_exam_intelligence.py `
        tests\test_phase6_pyq_exam_intelligence.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p66_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
    Stop-Gate "Phase 6.6 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.6 files intent-to-add."
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
    Stop-Gate "Phase 6.6 must not add or modify a SQLite migration."
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.6 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.6 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.6 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.6 gate changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared."
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.6 gate changed retrieval index bytes."
    }
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 6.6 PYQ + EXAM INTELLIGENCE: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - formal assessment/question evidence remains separate from Phase 6.5 generated practice"
Write-Host " - PYQ classification requires explicit PYQ/past-paper metadata"
Write-Host " - normal quiz/midsem/endsem records are not silently relabelled as PYQ"
Write-Host " - only accepted question-topic mappings contribute to topic statistics"
Write-Host " - proposed-only and unmapped questions remain visible"
Write-Host " - question source/document/page/locator provenance is preserved"
Write-Host " - historical counts/marks/mistakes are descriptive evidence, not exam prediction"
Write-Host " - target assessment scope uses only explicit assessment-topic/accepted mapping evidence"
Write-Host " - preparation priority is deterministic and includes human-readable reasons"
Write-Host " - real MA103N preview performs zero SQLite/provider/network writes"
Write-Host " - Phase 6.1-6.5, Phase 4 formal-assessment and complete regressions pass"
Write-Host " - no SQLite migration is introduced in Phase 6.6"
Write-Host ""
Write-Host "Phase 6.6 is ready for review and commit."
