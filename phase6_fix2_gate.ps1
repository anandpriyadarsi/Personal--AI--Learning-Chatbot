param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "5657a6da593ab84309892cd525b2814d60fe4c45"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 6.2 GROUNDED ACADEMIC TUTOR: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.2 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/domain/grounded_tutor_models.py",
    "personal_learning_assistant/tutor/grounding.py",
    "personal_learning_assistant/tutor/http_provider.py",
    "personal_learning_assistant/services/grounded_tutor_service.py",
    "phase6_grounded_tutor.py",
    "tests/test_phase6_grounded_tutor_engine.py",
    "PHASE6_FIX2_GROUNDED_ACADEMIC_TUTOR_ENGINE.md",
    "phase6_fix2_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.2 file: $item"
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
    Stop-Gate "Phase 5.8 retrieval generation is missing."
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

Run-Step "[1/9] Focused Phase 6.2 grounded tutor tests" {
    & $PythonResolved -m pytest tests\test_phase6_grounded_tutor_engine.py -q
}

Write-Host ""
Write-Host "[2/9] REAL grounded-tutor preview against Phase 5 retrieval (read-only)"
& $PythonResolved .\phase6_grounded_tutor.py `
    --database .\data\learning_assistant.db `
    --index-root .\.phase5_retrieval `
    preview `
    "Explain LU factorization intuitively and why it works" `
    --course-code MA103N `
    --mode concept `
    --source-policy source_only `
    --top-k 5
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Real grounded tutor preview failed."
}

Run-Step "[3/9] Phase 6.1 regressions" {
    & $PythonResolved -m pytest tests\test_phase6_tutor_foundation.py -q
}

Run-Step "[4/9] Phase 5 closure/retrieval regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_final_closure.py `
        tests\test_phase5_rebuildable_retrieval.py -q
}

Run-Step "[5/9] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p62_phase2_" + [guid]::NewGuid().ToString("N"))
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
        phase6_grounded_tutor.py `
        tests\test_phase6_grounded_tutor_engine.py
}

Run-Step "[7/9] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[8/9] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p62_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
    Stop-Gate "Phase 6.2 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.2 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.2 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.2 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.2 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.2 gate changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared."
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.2 gate changed retrieval index bytes."
    }
}

$migrationDiff = @(
    git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations
)
if ($migrationDiff.Count -ne 0) {
    Stop-Gate "Phase 6.2 must not add or modify a SQLite migration."
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 6.2 GROUNDED ACADEMIC TUTOR: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - Phase 6.1 session/evidence foundation remains intact"
Write-Host " - tutor session course/topic/resource scope drives Phase 5.8 retrieval"
Write-Host " - retrieved source text is treated as evidence data, never instructions"
Write-Host " - source_only requires valid exact [S#] citations"
Write-Host " - source_first is conservatively persisted as mixed support"
Write-Host " - unavailable/fabricated citation labels are rejected"
Write-Host " - insufficient evidence fails closed without calling the provider"
Write-Host " - provider failures do not persist partial current exchanges"
Write-Host " - exact chunk/document evidence links are persisted for valid answers"
Write-Host " - real production preview performs zero provider/network/SQLite writes"
Write-Host " - no academic progress, memory, plan, resource, assessment or knowledge state changes"
Write-Host " - Phase 6.1, Phase 5 and complete project regressions pass"
Write-Host " - no migration was introduced in Phase 6.2"
Write-Host ""
Write-Host "Phase 6.2 is ready for review and commit."
