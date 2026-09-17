param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$BaseCommit = "2e60247299aaec64cd785e993ade714e0a600b7f"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=================================================="
    Write-Host " PHASE 7.5.9 ACADEMIC AGENT WEB: BLOCKED"
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

function Hash-Files {
    param([string[]]$Paths)
    $result = @{}
    foreach ($path in $Paths) {
        if (Test-Path $path -PathType Leaf) {
            $resolved = (Resolve-Path $path).Path
            $result[$resolved] = (Get-FileHash $resolved -Algorithm SHA256).Hash
        }
    }
    return $result
}

function Hash-Tree {
    param([string]$Root)
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        Get-ChildItem $Root -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
            $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    }
    return $result
}

function Assert-Hashes-Unchanged {
    param([hashtable]$Before,[string]$Label)
    foreach ($path in $Before.Keys) {
        if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "$Label removed file: $path" }
        $after = (Get-FileHash $path -Algorithm SHA256).Hash
        if ($after -ne $Before[$path]) { Stop-Gate "$Label changed file: $path" }
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
if ($branch -ne $ExpectedBranch) { Stop-Gate "Expected $ExpectedBranch but found $branch." }
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) { Stop-Gate "Expected uncommitted Phase 7.5.9 work on $BaseCommit but found $head." }

$allowed = @(
    "personal_learning_assistant/services/academic_agent_web_service.py",
    "personal_learning_assistant/repositories/sqlite/tutor_repository.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/agent.html",
    "personal_learning_assistant/ui/web/templates/agent_session.html",
    "tests/test_phase7_5_academic_agent_web.py",
    "PHASE7_5_FIX9_ACADEMIC_AGENT_WEB.md",
    "phase7_5_fix9_gate.ps1"
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
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing Phase 7.5.9 file: $item" }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) { Stop-Gate "Production SQLite database is missing." }
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) { Stop-Gate "Current Phase 5.8 retrieval generation is missing." }

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = $null
if (Test-Path ".\.phase4_authority.json" -PathType Leaf) {
    $authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
}
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$indexBefore = Hash-Tree ".\.phase5_retrieval"

$protectedPaths = @(
    "personal_learning_assistant/services/grounded_tutor_service.py",
    "personal_learning_assistant/services/academic_agent_cutover_service.py",
    "personal_learning_assistant/services/adaptive_mentor_service.py",
    "phase6_academic_agent.py",
    "phase6_grounded_tutor.py",
    "personal_learning_assistant/ui/web/static/css/app.css"
)
$protectedBefore = Hash-Files $protectedPaths
$tutorTreeBefore = Hash-Tree ".\personal_learning_assistant\tutor"
$retrievalCodeBefore = Hash-Tree ".\personal_learning_assistant\retrieval"

Run-Step "[1/10] Phase 7.5.9 focused tests" {
    & $PythonResolved -m pytest -q tests\test_phase7_5_academic_agent_web.py
}

Run-Step "[2/10] Lazy app startup + provider-unconfigured smoke test" {
    $oldUrl = $env:LLM_API_URL
    $oldKey = $env:LLM_API_KEY
    $oldModel = $env:LLM_MODEL
    try {
        $env:LLM_API_URL = ""
        $env:LLM_API_KEY = ""
        $env:LLM_MODEL = ""
        & $PythonResolved -c "import sys; from personal_learning_assistant.ui.web import create_app; app=create_app({'TESTING':True}); forbidden=('personal_learning_assistant.services.grounded_tutor_service','personal_learning_assistant.services.adaptive_mentor_service','personal_learning_assistant.retrieval.index_store','personal_learning_assistant.tutor.http_provider'); assert all(x not in sys.modules for x in forbidden); c=app.test_client(); r=c.get('/agent'); t=r.get_data(as_text=True); assert r.status_code==200; assert 'Academic Agent' in t; assert 'Not configured' in t"
    } finally {
        $env:LLM_API_URL = $oldUrl
        $env:LLM_API_KEY = $oldKey
        $env:LLM_MODEL = $oldModel
    }
}

Run-Step "[3/10] Real GET-only Academic Agent/session read smoke tests" {
    & $PythonResolved -c "import sqlite3; from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING':True}).test_client(); r=c.get('/agent'); assert r.status_code==200; assert c.post('/agent').status_code==405; db=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); row=db.execute('SELECT id FROM tutor_sessions ORDER BY updated_at DESC,created_at DESC,id DESC LIMIT 1').fetchone(); db.close(); assert row is None or c.get('/agent/sessions/'+str(row[0])).status_code==200"
}

Run-Step "[4/10] Isolated tutor-session + fake-provider grounded-answer persistence" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_academic_agent_web.py::test_ask_persists_grounded_exchange_and_only_tutor_tables_change `
        tests\test_phase7_5_academic_agent_web.py::test_provider_unavailable_is_safe_and_does_not_persist_normal_turns `
        tests\test_phase7_5_academic_agent_web.py::test_provider_request_failure_is_safe_and_does_not_persist_normal_turns `
        tests\test_phase7_5_academic_agent_web.py::test_insufficient_evidence_persists_bounded_response_without_provider_call
}

Run-Step "[5/10] Phase 7.5.1-7.5.8 web regressions" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py `
        tests\test_phase7_5_courses_topics.py `
        tests\test_phase7_5_assessments.py `
        tests\test_phase7_5_progress_planning.py `
        tests\test_phase7_5_calendar_grades.py `
        tests\test_phase7_5_notes_resources.py `
        tests\test_phase7_5_knowledge_rag.py
}

Run-Step "[6/10] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py `
        tests\test_phase7_consumer_watch.py
}

Run-Step "[7/10] Complete pytest suite" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p759_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[8/10] Python compilation + pip check + SQLite integrity/FK checks" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\services\academic_agent_web_service.py `
        personal_learning_assistant\repositories\sqlite\tutor_repository.py `
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_academic_agent_web.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); c.close()"
}

Write-Host ""
Write-Host "[9/10] Protected execution/retrieval/Phase 6 file hashes + forbidden source scan"
Assert-Hashes-Unchanged $protectedBefore "Protected Phase 6/web file"
Assert-Hashes-Unchanged $tutorTreeBefore "Tutor code"
Assert-Hashes-Unchanged $retrievalCodeBefore "Retrieval code"

$protectedDiff = @(git diff --name-only $BaseCommit -- `
    personal_learning_assistant/services/grounded_tutor_service.py `
    personal_learning_assistant/services/academic_agent_cutover_service.py `
    personal_learning_assistant/services/adaptive_mentor_service.py `
    personal_learning_assistant/tutor `
    personal_learning_assistant/retrieval `
    phase6_academic_agent.py `
    phase6_grounded_tutor.py `
    personal_learning_assistant/ui/web/static/css/app.css)
if ($protectedDiff.Count -ne 0) { Stop-Gate "Phase 7.5.9 changed protected files: $($protectedDiff -join ', ')" }

$productionWebFiles = @(
    "personal_learning_assistant/services/academic_agent_web_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/agent.html",
    "personal_learning_assistant/ui/web/templates/agent_session.html"
)
$sourceText = ($productionWebFiles | ForEach-Object { Get-Content $_ -Raw }) -join "`n"
foreach ($token in @("AcademicAgentService", "EXECUTE_ACADEMIC_AGENT_ACTION", ".execute(", "practice_quiz", "lecture_learning", "/execute")) {
    if ($sourceText.Contains($token)) { Stop-Gate "Forbidden Phase 6.8 execution token in web production code: $token" }
}

Write-Host ""
Write-Host "[10/10] Scoped Git diff + production-data hash reconciliation"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "Phase 7.5.9 gate expects no pre-staged changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.9 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\","/")
        if (-not $allowedSet.ContainsKey($normalized)) { Stop-Gate "Phase 7.5.9 changed an out-of-scope file: $normalized" }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "Phase 7.5.9 changed production SQLite." }
if ($null -ne $authorityBefore) {
    if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) { Stop-Gate "Phase 7.5.9 removed authority control." }
    if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "Phase 7.5.9 changed authority control." }
}
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Phase 7.5.9 removed legacy JSON: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) { Stop-Gate "Phase 7.5.9 changed legacy JSON: $path" }
}
foreach ($path in $indexBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Phase 7.5.9 removed retrieval-index file: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $indexBefore[$path]) { Stop-Gate "Phase 7.5.9 changed retrieval-index file: $path" }
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 7.5.9 ACADEMIC AGENT WEB: PASS"
Write-Host "=================================================="
Write-Host "Mentor advice is advisory/read-only."
Write-Host "Tutor conversations persist only in tutor session/turn/evidence state."
Write-Host "Source Only is the default; Source First is explicit opt-in."
Write-Host "No Phase 6.8 action execution is exposed in the browser."
Write-Host "Production academic data and retrieval indexes were unchanged by the gate."
Write-Host "Phase 7.5.9 is ready for review and commit."
