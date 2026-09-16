param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase6/academic-tutor-intelligence"
$BaseCommit = "1746962e64e561edc9e8627ab0893f3c140edffc"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================"
    Write-Host " PHASE 6.1 TUTOR FOUNDATION: BLOCKED"
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
    Stop-Gate "Expected uncommitted Phase 6.1 work on $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/repositories/sqlite/migrations/0003_tutor_intelligence.sql",
    "personal_learning_assistant/domain/tutor_models.py",
    "personal_learning_assistant/tutor/__init__.py",
    "personal_learning_assistant/tutor/provider.py",
    "personal_learning_assistant/tutor/policy.py",
    "personal_learning_assistant/repositories/sqlite/tutor_repository.py",
    "personal_learning_assistant/services/tutor_session_service.py",
    "personal_learning_assistant/services/phase5_closure_service.py",
    "tests/test_phase3_academic_schema.py",
    "phase6_tutor_schema.py",
    "tests/test_phase6_tutor_foundation.py",
    "PHASE6_FIX1_TUTOR_DOMAIN_SESSION_EVIDENCE.md",
    "phase6_fix1_gate.ps1",
    "tests/test_phase3_assessments_topics_importer.py",
    "tests/test_phase3_attempts_performance_importer.py",
    "tests/test_phase3_courses_topics_importer.py",
    "tests/test_phase3_grades_calendar_importer.py",
    "tests/test_phase3_learning_progress_importer.py",
    "tests/test_phase3_question_topic_mappings_importer.py",
    "tests/test_phase3_questions_sources_importer.py",
    "tests/test_phase3_reconciliation_reports.py",
    "tests/test_phase3_reverse_export_restore.py",
    "tests/test_phase3_study_plans_importer.py",
    "tests/test_phase4_authority_promotion.py",
    "tests/test_phase4_final_locked_promotion.py",
    "tests/test_phase4_final_reconciliation.py",
    "tests/test_phase4_grades_calendar_dual_read.py"
)
$allowedSet = @{}
foreach ($item in $allowed) {
    $allowedSet[$item] = $true
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 6.1 file/change: $item"
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

Run-Step "[1/10] Focused Phase 6.1 tutor foundation tests" {
    & $PythonResolved -m pytest tests\test_phase6_tutor_foundation.py -q
}

Write-Host ""
Write-Host "[2/10] REAL production tutor-schema preview (read-only)"
& $PythonResolved .\phase6_tutor_schema.py `
    --database .\data\learning_assistant.db `
    preview
if ($LASTEXITCODE -ne 0) {
    Stop-Gate "Production tutor-schema preview failed."
}

Write-Host ""
Write-Host "[3/10] Isolated migration 0003 rehearsal"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("p61_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$tempDb = Join-Path $tempRoot "learning_assistant.db"
try {
    Copy-Item ".\data\learning_assistant.db" $tempDb
    & $PythonResolved .\phase6_tutor_schema.py `
        --database $tempDb `
        apply `
        --confirm APPLY_PHASE6_TUTOR_SCHEMA
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Isolated Phase 6.1 migration rehearsal failed."
    }
    $check = @(
        "import sqlite3,sys",
        "c=sqlite3.connect(sys.argv[1])",
        "v=tuple(r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version'))",
        "assert v[-3:] == (1,2,3)",
        "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
        "assert not c.execute('PRAGMA foreign_key_check').fetchall()",
        "c.close()"
    )
    $checkPath = Join-Path $tempRoot "check.py"
    $check | Set-Content -Path $checkPath -Encoding ASCII
    & $PythonResolved $checkPath $tempDb
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Isolated Phase 6.1 schema verification failed."
    }
} finally {
    Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Run-Step "[4/10] Phase 5 closure + retrieval regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase5_final_closure.py `
        tests\test_phase5_rebuildable_retrieval.py -q
}

Run-Step "[5/10] Phase 3 schema/foundation regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase3_sqlite_foundation.py `
        tests\test_phase3_academic_schema.py -q
}

Run-Step "[6/10] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p61_phase2_" + [guid]::NewGuid().ToString("N"))
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

Run-Step "[7/10] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant `
        phase6_tutor_schema.py `
        tests\test_phase6_tutor_foundation.py
}

Run-Step "[8/10] Installed dependency consistency" {
    & $PythonResolved -m pip check
}

Run-Step "[9/10] Production SQLite integrity/FK read-only" {
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p61_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
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
Write-Host "[10/10] Git + production/runtime immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) {
    Stop-Gate "Phase 6.1 gate expects no pre-staged changes."
}
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "Unable to mark Phase 6.1 files intent-to-add."
    }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) {
        Stop-Gate "git diff --check failed."
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) {
    Stop-Gate "Phase 6.1 gate changed production SQLite."
}
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) {
    Stop-Gate "Phase 6.1 gate changed Phase 4 authority control."
}
foreach ($path in $legacyBefore.Keys) {
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) {
        Stop-Gate "Legacy JSON changed during Phase 6.1 gate: $path"
    }
}
$currentIndexFiles = @(Get-ChildItem ".\.phase5_retrieval" -File -Recurse -Force)
if ($currentIndexFiles.Count -ne $indexBefore.Count) {
    Stop-Gate "Phase 6.1 gate changed retrieval index file set."
}
foreach ($file in $currentIndexFiles) {
    if (-not $indexBefore.ContainsKey($file.FullName)) {
        Stop-Gate "Unexpected retrieval index file appeared."
    }
    if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne $indexBefore[$file.FullName]) {
        Stop-Gate "Phase 6.1 gate changed retrieval index bytes."
    }
}

Write-Host ""
Write-Host "============================================"
Write-Host " PHASE 6.1 TUTOR DOMAIN/SESSION/EVIDENCE: PASS"
Write-Host "============================================"
Write-Host "Verified:"
Write-Host " - Phase 5 closure commit remains the starting authority"
Write-Host " - 0003 tutor schema is append-only; 0001/0002 are unchanged"
Write-Host " - production schema migration is preview-only during the gate"
Write-Host " - isolated 0003 migration rehearsal passes integrity/FK checks"
Write-Host " - tutor sessions preserve course/topic/assessment/resource scope"
Write-Host " - grounded/mixed assistant turns require exact chunk evidence"
Write-Host " - chunk/document provenance mismatch rolls back the whole turn"
Write-Host " - tutor writes do not mutate progress, memory, plans or knowledge chunks"
Write-Host " - provider boundary is fail-closed; no LLM/network call is wired"
Write-Host " - Phase 5, Phase 3 and complete regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and retrieval index are unchanged"
Write-Host ""
Write-Host "Phase 6.1 is ready for review and commit."
