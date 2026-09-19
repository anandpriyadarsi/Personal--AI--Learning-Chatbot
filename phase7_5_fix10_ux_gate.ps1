param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "main"
$BaseCommit = "2eb67c7dd872dc57315aec1225340fffbe9586d9"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=================================================="
    Write-Host " PHASE 7.5.10 ANVAYA UX REFINEMENT: BLOCKED"
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
            ForEach-Object {
                $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
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
        Get-ChildItem $Root -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
            $relative = $_.FullName.Substring($resolvedRoot.Length).TrimStart("\","/").Replace("\","/")
            if (-not $excluded.ContainsKey($relative)) {
                $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
        }
    }
    return $result
}

function Assert-Tree-Unchanged {
    param([hashtable]$Before,[string]$Root,[string]$Label)
    $after = Hash-Tree $Root
    if ($after.Count -ne $Before.Count) { Stop-Gate "$Label file count changed." }
    foreach ($path in $Before.Keys) {
        if (-not $after.ContainsKey($path)) { Stop-Gate "$Label removed file: $path" }
        if ($after[$path] -ne $Before[$path]) { Stop-Gate "$Label changed file: $path" }
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
if ($head -ne $BaseCommit) { Stop-Gate "Expected uncommitted UX refinement on $BaseCommit but found $head." }

$allowed = @(
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/home.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "tests/test_phase7_5_anvaya_shell.py",
    "tests/test_phase7_5_home_dashboard.py",
    "tests/test_phase7_5_anvaya_ux_refinement.py",
    "PHASE7_5_FIX10_UX_REFINEMENT.md",
    "phase7_5_fix10_ux_gate.ps1"
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
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing UX refinement file: $item" }
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
$routeBefore = (Get-FileHash ".\personal_learning_assistant\ui\web\routes.py" -Algorithm SHA256).Hash
$servicesBefore = Hash-Tree ".\personal_learning_assistant\services"
$repositoriesBefore = Hash-Tree ".\personal_learning_assistant\repositories"
$tutorBefore = Hash-Tree ".\personal_learning_assistant\tutor"
$retrievalCodeBefore = Hash-Tree ".\personal_learning_assistant\retrieval"
$templatesBefore = Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("base.html","home.html")
$jsBefore = (Get-FileHash ".\personal_learning_assistant\ui\web\static\js\app.js" -Algorithm SHA256).Hash
$brandBefore = Hash-Tree ".\personal_learning_assistant\ui\web\static\brand"

Run-Step "[1/8] Focused ANVAYA UX refinement + shell + Home tests" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_anvaya_ux_refinement.py `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_home_dashboard.py
}

Run-Step "[2/8] Existing Phase 7.5 web regression tests" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py `
        tests\test_phase7_5_courses_topics.py `
        tests\test_phase7_5_assessments.py `
        tests\test_phase7_5_progress_planning.py `
        tests\test_phase7_5_calendar_grades.py `
        tests\test_phase7_5_notes_resources.py `
        tests\test_phase7_5_knowledge_rag.py `
        tests\test_phase7_5_academic_agent_web.py `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_anvaya_ux_refinement.py
}

Run-Step "[3/8] Current workspace + static asset smoke tests" {
    & $PythonResolved -c "from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING':True}).test_client(); paths=('/', '/agent', '/notes', '/resources', '/knowledge', '/courses', '/assessments', '/calendar', '/planning'); results=[(p,c.get(p).status_code) for p in paths]; assert all(s==200 for p,s in results), results; t=c.get('/').get_data(as_text=True); assert 'What do you want to work on?' in t; assert 'Phase 7.5.2' not in t; assert 'read-only view' not in t; assert c.get('/static/css/app.css').status_code==200"
}

Write-Host ""
Write-Host "[4/8] Presentation scope / UX contract scan"
$baseSource = Get-Content ".\personal_learning_assistant\ui\web\templates\base.html" -Raw
$homeSource = Get-Content ".\personal_learning_assistant\ui\web\templates\home.html" -Raw
$cssSource = Get-Content ".\personal_learning_assistant\ui\web\static\css\app.css" -Raw
foreach ($token in @("Academic workspace", "Local-first", 'class="nav-more"', 'aria-disabled="true"')) {
    if (-not $baseSource.Contains($token)) { Stop-Gate "Missing refined shell token: $token" }
}
foreach ($token in @("What do you want to work on?", "Open ANVAYA Tutor", "home-command-center", "quick-actions", "ANVAYA recommends")) {
    if (-not $homeSource.Contains($token)) { Stop-Gate "Missing refined Home token: $token" }
}
foreach ($token in @("Phase 7.5.2", "read-only view", "web.tasks", "web.obsidian")) {
    if ($homeSource.Contains($token)) { Stop-Gate "Forbidden Home UX token: $token" }
}
foreach ($token in @("grid-template-columns: 15rem minmax(0, 1fr)", "width: min(9.5rem, 100%)", ".home-command-center", ".home-summary")) {
    if (-not $cssSource.Contains($token)) { Stop-Gate "Missing compact UX CSS token: $token" }
}
foreach ($token in @("http://", "https://", "@import url(", "fonts.googleapis", "cdnjs", "unpkg", "jsdelivr")) {
    if (($baseSource + "`n" + $homeSource + "`n" + $cssSource).ToLowerInvariant().Contains($token.ToLowerInvariant())) {
        Stop-Gate "Remote UI dependency found in refinement files: $token"
    }
}
Write-Host "Presentation scope and UX contract are present."

Run-Step "[5/8] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_runtime_inventory.py `
        tests\test_phase7_recovery_bundle.py `
        tests\test_phase7_restore_rehearsal.py `
        tests\test_phase7_consumer_watch.py
}

Run-Step "[6/8] Complete pytest suite" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p7510ux_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item ".\tests\test_phase2_closure_architecture.py" (Join-Path $temp "tests\test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest ((Join-Path $temp "tests\test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[7/8] Python compilation + pip check + SQLite integrity/FK checks" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_anvaya_ux_refinement.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); c.close()"
}

Write-Host ""
Write-Host "[8/8] Protected hashes + scoped diff + production-data reconciliation"
if ((Get-FileHash ".\personal_learning_assistant\ui\web\routes.py" -Algorithm SHA256).Hash -ne $routeBefore) { Stop-Gate "Web routes changed during UX refinement." }
Assert-Tree-Unchanged $servicesBefore ".\personal_learning_assistant\services" "Services"
Assert-Tree-Unchanged $repositoriesBefore ".\personal_learning_assistant\repositories" "Repositories"
Assert-Tree-Unchanged $tutorBefore ".\personal_learning_assistant\tutor" "Tutor code"
Assert-Tree-Unchanged $retrievalCodeBefore ".\personal_learning_assistant\retrieval" "Retrieval code"
if ((Get-FileHash ".\personal_learning_assistant\ui\web\static\js\app.js" -Algorithm SHA256).Hash -ne $jsBefore) { Stop-Gate "Mobile navigation JavaScript changed during UX refinement." }
$brandAfter = Hash-Tree ".\personal_learning_assistant\ui\web\static\brand"
if ($brandAfter.Count -ne $brandBefore.Count) { Stop-Gate "Brand asset file count changed." }
foreach ($path in $brandBefore.Keys) {
    if (-not $brandAfter.ContainsKey($path) -or $brandAfter[$path] -ne $brandBefore[$path]) { Stop-Gate "Brand asset changed: $path" }
}
$templatesAfter = Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("base.html","home.html")
if ($templatesAfter.Count -ne $templatesBefore.Count) { Stop-Gate "Template file count changed outside base/home." }
foreach ($path in $templatesBefore.Keys) {
    if (-not $templatesAfter.ContainsKey($path) -or $templatesAfter[$path] -ne $templatesBefore[$path]) { Stop-Gate "Template changed outside base/home: $path" }
}

$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "UX refinement gate expects no pre-staged changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark UX refinement files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\","/")
        if (-not $allowedSet.ContainsKey($normalized)) { Stop-Gate "UX refinement changed an out-of-scope file: $normalized" }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "UX refinement changed production SQLite." }
if ($null -ne $authorityBefore) {
    if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) { Stop-Gate "UX refinement removed authority control." }
    if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "UX refinement changed authority control." }
}
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "UX refinement removed legacy JSON: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) { Stop-Gate "UX refinement changed legacy JSON: $path" }
}
$indexAfter = Hash-Tree ".\.phase5_retrieval"
if ($indexAfter.Count -ne $indexBefore.Count) { Stop-Gate "UX refinement changed retrieval-index file count." }
foreach ($path in $indexBefore.Keys) {
    if (-not $indexAfter.ContainsKey($path) -or $indexAfter[$path] -ne $indexBefore[$path]) { Stop-Gate "UX refinement changed retrieval-index file: $path" }
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 7.5.10 ANVAYA UX REFINEMENT: PASS"
Write-Host "=================================================="
Write-Host "Home is action-first and the desktop shell is more compact."
Write-Host "No new academic write capability was introduced."
Write-Host "Routes, backend semantics, production academic data, and retrieval indexes remained unchanged."
Write-Host "The refinement is ready for review and a single scoped commit."
