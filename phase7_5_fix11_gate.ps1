param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "main"
$PlanPath = "docs/superpowers/plans/2026-09-19-phase7-5-11-operational-notes-resources.md"
$BaseCommitRaw = git log -1 --format=%H -- $PlanPath
if ([string]::IsNullOrWhiteSpace($BaseCommitRaw)) {
    Write-Host "PHASE 7.5.11 OPERATIONAL NOTES + RESOURCES: BLOCKED"
    Write-Host "The Phase 7.5.11 plan must be committed separately before the implementation gate runs."
    exit 1
}
$BaseCommit = $BaseCommitRaw.Trim()

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host " PHASE 7.5.11 OPERATIONAL NOTES + RESOURCES: BLOCKED"
    Write-Host "============================================================"
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

function Hash-Tree {
    param([string]$Root)
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        Get-ChildItem $Root -File -Recurse -Force |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object FullName |
            ForEach-Object { $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
    }
    return $result
}

function Hash-Tree-Except {
    param([string]$Root,[string[]]$RelativeExcludes)
    $excluded = @{}
    foreach ($item in $RelativeExcludes) { $excluded[$item.Replace("\","/")] = $true }
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        $resolvedRoot = (Resolve-Path $Root).Path
        Get-ChildItem $Root -File -Recurse -Force |
            Where-Object {
                $_.Extension -notin @(".pyc", ".pyo") -and
                $_.FullName -notmatch '[\\/]__pycache__[\\/]'
            } |
            Sort-Object FullName |
            ForEach-Object {
                $relative = $_.FullName.Substring($resolvedRoot.Length).TrimStart("\","/").Replace("\","/")
                if (-not $excluded.ContainsKey($relative)) {
                    $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
                }
            }
    }
    return $result
}

function Assert-Hash-Map-Unchanged {
    param([hashtable]$Before,[hashtable]$After,[string]$Label)
    if ($After.Count -ne $Before.Count) { Stop-Gate "$Label file count changed." }
    foreach ($path in $Before.Keys) {
        if (-not $After.ContainsKey($path)) { Stop-Gate "$Label removed file: $path" }
        if ($After[$path] -ne $Before[$path]) { Stop-Gate "$Label changed file: $path" }
    }
}

if (Test-Path $Python) { $PythonResolved = (Resolve-Path $Python).Path }
else {
    $cmd = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Stop-Gate "Python interpreter not found." }
    $PythonResolved = $cmd.Source
}

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { Stop-Gate "Expected $ExpectedBranch but found $branch." }
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) { Stop-Gate "Expected uncommitted Phase 7.5.11 implementation on plan commit $BaseCommit but found $head." }

$allowed = @(
    "personal_learning_assistant/domain/note_models.py",
    "personal_learning_assistant/repositories/interfaces.py",
    "personal_learning_assistant/repositories/json/note_repository.py",
    "personal_learning_assistant/services/notes_service.py",
    "personal_learning_assistant/services/notes_resources_dashboard_service.py",
    "personal_learning_assistant/services/notes_resources_web_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/notes.html",
    "personal_learning_assistant/ui/web/templates/resources.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "tests/test_phase2_notes_service.py",
    "tests/test_phase2_notes_write_adapter.py",
    "tests/test_phase7_5_notes_resources.py",
    "tests/test_phase7_5_operational_notes_resources.py",
    "PHASE7_5_FIX11_OPERATIONAL_NOTES_RESOURCES.md",
    "phase7_5_fix11_gate.ps1"
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
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing Phase 7.5.11 file: $item" }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) { Stop-Gate "Production SQLite database is missing." }
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) { Stop-Gate "Current Phase 5 retrieval generation is missing." }

$dbBefore = (Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash
$authorityBefore = $null
if (Test-Path ".\.phase4_authority.json" -PathType Leaf) { $authorityBefore = (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash }
$legacyBefore = @{}
Get-ChildItem ".\data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object { $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
$indexBefore = Hash-Tree ".\.phase5_retrieval"

$protectedServices = Hash-Tree-Except ".\personal_learning_assistant\services" @(
    "notes_service.py",
    "notes_resources_dashboard_service.py",
    "notes_resources_web_service.py"
)
$protectedRepositories = Hash-Tree-Except ".\personal_learning_assistant\repositories" @(
    "interfaces.py",
    "json/note_repository.py"
)
$protectedDomain = Hash-Tree-Except ".\personal_learning_assistant\domain" @("note_models.py")
$protectedTutor = Hash-Tree ".\personal_learning_assistant\tutor"
$protectedRetrieval = Hash-Tree ".\personal_learning_assistant\retrieval"
$protectedTemplates = Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("notes.html","resources.html")
$jsBefore = (Get-FileHash ".\personal_learning_assistant\ui\web\static\js\app.js" -Algorithm SHA256).Hash

Run-Step "[1/10] Phase 7.5.11 focused operational tests" {
    & $PythonResolved -m pytest -q tests\test_phase7_5_operational_notes_resources.py tests\test_phase7_5_notes_resources.py
}

Run-Step "[2/10] Phase 2 Notes + Resources service/repository regressions" {
    & $PythonResolved -m pytest -q `
        tests\test_phase2_notes_service.py `
        tests\test_phase2_notes_write_adapter.py `
        tests\test_phase2_notes_cli_adapter.py `
        tests\test_phase2_resources_service.py `
        tests\test_phase2_resources_cli_adapter.py `
        tests\test_phase2_repository_protocols.py
}

Run-Step "[3/10] All Phase 7.5 web regressions" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py `
        tests\test_phase7_5_courses_topics.py `
        tests\test_phase7_5_assessments.py `
        tests\test_phase7_5_progress_planning.py `
        tests\test_phase7_5_calendar_grades.py `
        tests\test_phase7_5_notes_resources.py `
        tests\test_phase7_5_operational_notes_resources.py `
        tests\test_phase7_5_knowledge_rag.py `
        tests\test_phase7_5_academic_agent_web.py `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_anvaya_ux_refinement.py
}

Run-Step "[4/10] GET read-purity tests against temporary stores" {
    & $PythonResolved -m pytest -q `
        tests\test_phase2_notes_service.py::test_read_queries_leave_notes_json_hash_unchanged `
        tests\test_phase2_notes_service.py::test_missing_empty_invalid_and_non_list_stores_are_read_only_empty `
        tests\test_phase2_notes_service.py::test_get_note_uses_position_without_mutating_store `
        tests\test_phase2_resources_service.py::test_zero_byte_legacy_file_reads_empty_without_rewrite `
        tests\test_phase2_resources_service.py::test_missing_file_read_does_not_create_file `
        tests\test_phase2_resources_service.py::test_invalid_json_read_does_not_repair_source `
        tests\test_phase2_resources_service.py::test_all_service_read_queries_leave_hash_unchanged
}

Run-Step "[5/10] POST write tests against temporary stores + PRG/status validation" {
    & $PythonResolved -m pytest -q tests\test_phase7_5_operational_notes_resources.py -k "post or create or update or invalid or duplicate or zero_byte or storage"
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
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p7511_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally { Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue }
}

Run-Step "[8/10] Python compile + pip check + SQLite integrity/FK checks" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\domain\note_models.py `
        personal_learning_assistant\repositories\json\note_repository.py `
        personal_learning_assistant\services\notes_service.py `
        personal_learning_assistant\services\notes_resources_dashboard_service.py `
        personal_learning_assistant\services\notes_resources_web_service.py `
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_operational_notes_resources.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); c.close()"
}

Write-Host ""
Write-Host "[9/10] Protected backend/authority/retrieval hashes + forbidden dependency-direction scan"
Assert-Hash-Map-Unchanged $protectedServices (Hash-Tree-Except ".\personal_learning_assistant\services" @("notes_service.py","notes_resources_dashboard_service.py","notes_resources_web_service.py")) "Protected services"
Assert-Hash-Map-Unchanged $protectedRepositories (Hash-Tree-Except ".\personal_learning_assistant\repositories" @("interfaces.py","json/note_repository.py")) "Protected repositories"
Assert-Hash-Map-Unchanged $protectedDomain (Hash-Tree-Except ".\personal_learning_assistant\domain" @("note_models.py")) "Protected domain"
Assert-Hash-Map-Unchanged $protectedTutor (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Hash-Map-Unchanged $protectedRetrieval (Hash-Tree ".\personal_learning_assistant\retrieval") "Retrieval code"
Assert-Hash-Map-Unchanged $protectedTemplates (Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("notes.html","resources.html")) "Other web templates"
if ((Get-FileHash ".\personal_learning_assistant\ui\web\static\js\app.js" -Algorithm SHA256).Hash -ne $jsBefore) { Stop-Gate "Web JavaScript changed outside Phase 7.5.11 scope." }
$routeSource = Get-Content ".\personal_learning_assistant\ui\web\routes.py" -Raw
foreach ($token in @("repositories.json.note_repository", "repositories.json.resource_repository", "import notes", "import resources", "import main")) {
    if ($routeSource.Contains($token)) { Stop-Gate "Forbidden route dependency found: $token" }
}
$webServiceSource = Get-Content ".\personal_learning_assistant\services\notes_resources_web_service.py" -Raw
foreach ($token in @("import main", "from main", "import notes", "import resources", "input(", "print(")) {
    if ($webServiceSource.Contains($token)) { Stop-Gate "Forbidden web-service dependency found: $token" }
}

Write-Host ""
Write-Host "[10/10] Scoped git diff + production-data/retrieval-index hash reconciliation"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "Phase 7.5.11 gate expects no pre-staged implementation changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.11 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\","/")
        if (-not $allowedSet.ContainsKey($normalized)) { Stop-Gate "Phase 7.5.11 changed an out-of-scope file: $normalized" }
    }
} finally { git reset --quiet -- $allowed 2>$null }

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "Tests changed production SQLite." }
if ($null -ne $authorityBefore) {
    if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) { Stop-Gate "Tests removed authority control." }
    if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "Tests changed authority control." }
}
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Tests removed production JSON: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) { Stop-Gate "Tests changed production JSON: $path" }
}
$indexAfter = Hash-Tree ".\.phase5_retrieval"
Assert-Hash-Map-Unchanged $indexBefore $indexAfter "Retrieval index"

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 7.5.11 OPERATIONAL NOTES + RESOURCES: PASS"
Write-Host "============================================================"
Write-Host "Notes support create/search/filter/edit through the web service boundary."
Write-Host "Resources support add/search/filter/status updates through the web service boundary."
Write-Host "GET reads remained side-effect free and all explicit writes use POST + 303."
Write-Host "Production academic data, SQLite authority, and retrieval indexes were unchanged by the gate."
