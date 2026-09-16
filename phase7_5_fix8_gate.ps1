param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "7f46e073eb05a0c8a2b9db2c8e17f1bd41af4b9c"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=================================================="
    Write-Host " PHASE 7.5.8 KNOWLEDGE BASE / RAG: BLOCKED"
    Write-Host "=================================================="
    Write-Host $Message
    exit 1
}

function Run-Step {
    param([string]$Label,[scriptblock]$Command)
    Write-Host ""
    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) { Stop-Gate "$Label failed with exit code $LASTEXITCODE." }
}

if (Test-Path $Python) {
    $PythonResolved = (Resolve-Path $Python).Path
} else {
    $cmd = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found." }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { Stop-Gate "Expected $ExpectedBranch but found $branch." }
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) { Stop-Gate "Expected uncommitted Phase 7.5.8 work on $BaseCommit but found $head." }

$allowed = @(
    "personal_learning_assistant/services/knowledge_dashboard_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/knowledge.html",
    "tests/test_phase7_5_knowledge_rag.py",
    "PHASE7_5_FIX8_KNOWLEDGE_RAG.md",
    "phase7_5_fix8_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }

foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) { Stop-Gate "Out-of-scope working-tree change: $path" }
}
foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing Phase 7.5.8 file: $item" }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) { Stop-Gate "Production SQLite database is missing." }
if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) { Stop-Gate "Phase 4 authority-control file is missing." }
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) { Stop-Gate "Current Phase 5 retrieval generation is missing." }

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

Run-Step "[1/10] Focused Phase 7.5.8 Knowledge Base / RAG tests" {
    & $PythonResolved -m pytest tests\test_phase7_5_knowledge_rag.py -q
}

Run-Step "[2/10] Real current Phase 5.8 retrieval-generation read" {
    & $PythonResolved -c "from personal_learning_assistant.services.knowledge_dashboard_service import load_knowledge_dashboard; d=load_knowledge_dashboard(); assert d['available'] is True; assert d['searched'] is False; assert d['index']['generation_id'] not in {'','Unknown'}; assert d['index']['chunk_count'] >= 0; assert d['index']['document_count'] >= 0; assert d['results'] == []; assert d['context']['source_count'] == 0"
}

Run-Step "[3/10] Real GET-only Knowledge route smoke test" {
    & $PythonResolved -c "from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING': True}).test_client(); r=c.get('/knowledge'); t=r.get_data(as_text=True); assert r.status_code == 200; assert 'Knowledge base &amp; RAG' in t; assert '<form' in t.lower(); assert c.post('/knowledge').status_code == 405; assert 'Search your indexed academic sources' in t"
}

Run-Step "[4/10] Phase 7.5.1-7.5.7 web regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py `
        tests\test_phase7_5_courses_topics.py `
        tests\test_phase7_5_assessments.py `
        tests\test_phase7_5_progress_planning.py `
        tests\test_phase7_5_calendar_grades.py `
        tests\test_phase7_5_notes_resources.py -q
}

Run-Step "[5/10] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py `
        tests\test_phase7_consumer_watch.py -q
}

Run-Step "[6/10] Complete suite (promotion-aware)" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p758_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[7/10] Python compilation" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\services\knowledge_dashboard_service.py `
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_knowledge_rag.py
}

Run-Step "[8/10] Dependency consistency + production SQLite integrity/FK" {
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $sqliteCheckPath = Join-Path ([IO.Path]::GetTempPath()) ("p758_sqlite_" + [guid]::NewGuid().ToString("N") + ".py")
    try {
        @(
            "import sqlite3",
            "c = sqlite3.connect('file:data/learning_assistant.db?mode=ro', uri=True)",
            "assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'",
            "assert not c.execute('PRAGMA foreign_key_check').fetchall()",
            "c.close()"
        ) | Set-Content -Path $sqliteCheckPath -Encoding ASCII
        & $PythonResolved $sqliteCheckPath
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $sqliteCheckPath -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "[9/10] Scope + completed-phase / retrieval immutability"
$migrationDiff = @(git diff --name-only $BaseCommit -- personal_learning_assistant/repositories/sqlite/migrations)
if ($migrationDiff.Count -ne 0) { Stop-Gate "Phase 7.5.8 must not add or modify SQLite migrations." }
$retrievalCodeDiff = @(git diff --name-only $BaseCommit -- personal_learning_assistant/retrieval semantic_retrieval.py hybrid_retrieval.py rag_answer.py knowledge.py)
if ($retrievalCodeDiff.Count -ne 0) { Stop-Gate "Phase 7.5.8 must not modify existing retrieval/RAG engines: $($retrievalCodeDiff -join ', ')" }

$protected = @(
    "personal_learning_assistant/phase7",
    "phase7_runtime_inventory.py",
    "phase7_recovery_bundle.py",
    "phase7_restore_rehearsal.py",
    "phase7_consumer_watch.py",
    "phase7_fix1_gate.ps1",
    "phase7_fix2_gate.ps1",
    "phase7_fix3_gate.ps1",
    "phase7_fix4_gate.ps1",
    "phase7_web.py",
    "requirements.txt",
    "personal_learning_assistant/ui/web/__init__.py",
    "personal_learning_assistant/ui/web/__main__.py",
    "personal_learning_assistant/ui/web/errors.py",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "personal_learning_assistant/services/home_dashboard_service.py",
    "personal_learning_assistant/services/course_dashboard_service.py",
    "personal_learning_assistant/services/assessment_dashboard_service.py",
    "personal_learning_assistant/services/planning_dashboard_service.py",
    "personal_learning_assistant/services/calendar_grades_dashboard_service.py",
    "personal_learning_assistant/services/notes_resources_dashboard_service.py",
    "personal_learning_assistant/ui/web/templates/home.html",
    "personal_learning_assistant/ui/web/templates/courses.html",
    "personal_learning_assistant/ui/web/templates/assessments.html",
    "personal_learning_assistant/ui/web/templates/planning.html",
    "personal_learning_assistant/ui/web/templates/calendar.html",
    "personal_learning_assistant/ui/web/templates/notes.html",
    "personal_learning_assistant/ui/web/templates/resources.html",
    "tests/test_phase7_5_web_foundation.py",
    "tests/test_phase7_5_home_dashboard.py",
    "tests/test_phase7_5_courses_topics.py",
    "tests/test_phase7_5_assessments.py",
    "tests/test_phase7_5_progress_planning.py",
    "tests/test_phase7_5_calendar_grades.py",
    "tests/test_phase7_5_notes_resources.py",
    "PHASE7_5_FIX1_WEB_FOUNDATION.md",
    "PHASE7_5_FIX2_HOME_ACADEMIC_BRIEF.md",
    "PHASE7_5_FIX3_COURSES_TOPICS.md",
    "PHASE7_5_FIX4_ASSESSMENTS.md",
    "PHASE7_5_FIX5_PROGRESS_PLANNING.md",
    "PHASE7_5_FIX6_CALENDAR_GRADES.md",
    "PHASE7_5_FIX7_NOTES_RESOURCES.md",
    "phase7_5_fix1_gate.ps1",
    "phase7_5_fix2_gate.ps1",
    "phase7_5_fix3_gate.ps1",
    "phase7_5_fix4_gate.ps1",
    "phase7_5_fix5_gate.ps1",
    "phase7_5_fix6_gate.ps1",
    "phase7_5_fix7_gate.ps1",
    "personal_learning_assistant/retrieval",
    "semantic_retrieval.py",
    "hybrid_retrieval.py",
    "rag_answer.py",
    "knowledge.py"
)
$protectedDiff = @(git diff --name-only $BaseCommit -- $protected)
if ($protectedDiff.Count -ne 0) { Stop-Gate "Phase 7.5.8 changed protected completed files: $($protectedDiff -join ', ')" }

Write-Host ""
Write-Host "[10/10] Git + production/runtime/index immutability"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "Phase 7.5.8 gate expects no pre-staged changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.8 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
} finally {
    git reset --quiet -- $allowed 2>$null
}

$trackedChanges = @(git diff --name-only $BaseCommit --)
foreach ($path in $trackedChanges) {
    $normalized = $path.Trim().Replace("\","/")
    if (-not $allowedSet.ContainsKey($normalized)) { Stop-Gate "Phase 7.5.8 changed an out-of-scope file: $normalized" }
}
if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "Phase 7.5.8 changed production SQLite." }
if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "Phase 7.5.8 changed authority control." }
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Phase 7.5.8 removed legacy JSON: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) { Stop-Gate "Phase 7.5.8 changed legacy JSON: $path" }
}
foreach ($path in $indexBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Phase 7.5.8 removed retrieval-index file: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $indexBefore[$path]) { Stop-Gate "Phase 7.5.8 changed retrieval-index file: $path" }
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 7.5.8 KNOWLEDGE BASE / RAG: PASS"
Write-Host "=================================================="
Write-Host "Verified:"
Write-Host " - Knowledge reads the existing Phase 5.8 current retrieval generation read-only"
Write-Host " - GET queries expose source-grounded retrieval hits and assembled RAG context"
Write-Host " - semantic-query failure degrades to lexical retrieval without rebuilding the index"
Write-Host " - retrieval, embedding and legacy RAG engines remain lazy at web-app creation"
Write-Host " - /knowledge is GET-only; its form changes only the query string"
Write-Host " - no LLM answer generation occurs in Phase 7.5.8"
Write-Host " - Phase 7.5.1-7.5.7, Phase 7.1-7.4 and complete regressions pass"
Write-Host " - production SQLite, authority, legacy JSON and complete retrieval index remain unchanged"
Write-Host " - no ingestion, index build/rebuild, academic mutation, migration, deletion or authority switch occurs"
Write-Host ""
Write-Host "Phase 7.5.8 is ready for review and commit."
