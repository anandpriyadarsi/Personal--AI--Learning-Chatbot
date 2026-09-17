param([string]$Python = ".\.venv\Scripts\python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7/deprecation-observation"
$PlanPath = "docs/superpowers/plans/2026-09-17-phase7-5-10-anvaya-product-shell.md"
$BaseCommit = (git log -1 --format=%H -- $PlanPath).Trim()

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "=================================================="
    Write-Host " PHASE 7.5.10 ANVAYA PRODUCT SHELL: BLOCKED"
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

function Hash-Tree-Except {
    param([string]$Root,[string[]]$ExcludedNames)
    $result = @{}
    if (Test-Path $Root -PathType Container) {
        Get-ChildItem $Root -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
            if ($ExcludedNames -notcontains $_.Name) {
                $result[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
            }
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

function Assert-Tree-Unchanged {
    param([hashtable]$Before,[string]$Root,[string]$Label)
    $after = Hash-Tree $Root
    if ($after.Count -ne $Before.Count) { Stop-Gate "$Label file count changed." }
    foreach ($path in $Before.Keys) {
        if (-not $after.ContainsKey($path)) { Stop-Gate "$Label removed file: $path" }
        if ($after[$path] -ne $Before[$path]) { Stop-Gate "$Label changed file: $path" }
    }
}

function Assert-PngSignature {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Leaf)) { Stop-Gate "Missing PNG: $Path" }
    $bytes = [IO.File]::ReadAllBytes((Resolve-Path $Path).Path)
    if ($bytes.Length -le 1024) { Stop-Gate "PNG is unexpectedly small: $Path" }
    $expected = @(0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A)
    for ($i = 0; $i -lt $expected.Count; $i++) {
        if ($bytes[$i] -ne $expected[$i]) { Stop-Gate "Invalid PNG signature: $Path" }
    }
}

if ([string]::IsNullOrWhiteSpace($BaseCommit)) { Stop-Gate "Unable to resolve the Phase 7.5.10 plan commit." }

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
if ($head -ne $BaseCommit) { Stop-Gate "Expected uncommitted Phase 7.5.10 work on plan commit $BaseCommit but found $head." }

$allowed = @(
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "personal_learning_assistant/ui/web/static/js/app.js",
    "personal_learning_assistant/ui/web/static/brand/anvaya-mark.png",
    "personal_learning_assistant/ui/web/static/brand/anvaya-wordmark-white.png",
    "tests/test_phase7_5_anvaya_shell.py",
    "tests/test_phase7_5_web_foundation.py",
    "docs/brand/ANVAYA_PRIMARY_LIGHT.png",
    "docs/brand/ANVAYA_README_BANNER.png",
    "docs/brand/ANVAYA_SPLASH.png",
    "docs/brand/ANVAYA_MINI_BRAND_GUIDE.png",
    "PHASE7_5_FIX10_ANVAYA_PRODUCT_SHELL.md",
    "phase7_5_fix10_gate.ps1"
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
    if (-not (Test-Path $item -PathType Leaf)) { Stop-Gate "Missing Phase 7.5.10 file: $item" }
}

if (-not (Test-Path ".\data\learning_assistant.db" -PathType Leaf)) { Stop-Gate "Production SQLite database is missing." }
if (-not (Test-Path ".\.phase5_retrieval\current.json" -PathType Leaf)) { Stop-Gate "Current Phase 5.8 retrieval generation is missing." }

Assert-PngSignature ".\personal_learning_assistant\ui\web\static\brand\anvaya-mark.png"
Assert-PngSignature ".\personal_learning_assistant\ui\web\static\brand\anvaya-wordmark-white.png"
foreach ($docAsset in @(
    ".\docs\brand\ANVAYA_PRIMARY_LIGHT.png",
    ".\docs\brand\ANVAYA_README_BANNER.png",
    ".\docs\brand\ANVAYA_SPLASH.png",
    ".\docs\brand\ANVAYA_MINI_BRAND_GUIDE.png"
)) {
    if (-not (Test-Path $docAsset -PathType Leaf)) { Stop-Gate "Missing documentation brand asset: $docAsset" }
    if ((Get-Item $docAsset).Length -le 1024) { Stop-Gate "Documentation brand asset is unexpectedly small: $docAsset" }
}

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

$routeBefore = Hash-Files @("personal_learning_assistant/ui/web/routes.py")
$servicesBefore = Hash-Tree ".\personal_learning_assistant\services"
$repositoriesBefore = Hash-Tree ".\personal_learning_assistant\repositories"
$tutorBefore = Hash-Tree ".\personal_learning_assistant\tutor"
$retrievalCodeBefore = Hash-Tree ".\personal_learning_assistant\retrieval"
$templatesBefore = Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("base.html")

Run-Step "[1/10] Phase 7.5.10 focused shell tests" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_web_foundation.py::test_home_route_renders_local_navigation_shell
}

Run-Step "[2/10] Existing Phase 7.5 web regression tests (7.5.1-7.5.9)" {
    & $PythonResolved -m pytest -q `
        tests\test_phase7_5_web_foundation.py `
        tests\test_phase7_5_home_dashboard.py `
        tests\test_phase7_5_courses_topics.py `
        tests\test_phase7_5_assessments.py `
        tests\test_phase7_5_progress_planning.py `
        tests\test_phase7_5_calendar_grades.py `
        tests\test_phase7_5_notes_resources.py `
        tests\test_phase7_5_knowledge_rag.py `
        tests\test_phase7_5_academic_agent_web.py
}

Run-Step "[3/10] Route + local static asset smoke tests" {
    & $PythonResolved -c "from personal_learning_assistant.ui.web import create_app; c=create_app({'TESTING':True}).test_client(); paths=('/', '/agent', '/notes', '/resources', '/knowledge', '/courses', '/assessments', '/calendar', '/planning'); results=[(p,c.get(p).status_code) for p in paths]; assert all(s==200 for p,s in results), results; assets=('/static/css/app.css','/static/js/app.js','/static/brand/anvaya-mark.png','/static/brand/anvaya-wordmark-white.png'); a=[(p,c.get(p).status_code,c.get(p).content_type) for p in assets]; assert all(s==200 for p,s,t in a), a"
}

Write-Host ""
Write-Host "[4/10] Local-asset / forbidden-URL scan"
$shellFiles = @(
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "personal_learning_assistant/ui/web/static/js/app.js"
)
$shellText = ($shellFiles | ForEach-Object { Get-Content $_ -Raw }) -join "`n"
foreach ($token in @("http://", "https://")) {
    if ($shellText.Contains($token)) { Stop-Gate "Remote URL found in production shell files: $token" }
}
foreach ($token in @("@import url(", "fonts.googleapis", "cdnjs", "unpkg", "jsdelivr")) {
    if ($shellText.ToLowerInvariant().Contains($token.ToLowerInvariant())) { Stop-Gate "Remote UI dependency token found: $token" }
}
Write-Host "Local shell assets contain no remote URL/CDN dependency."

Write-Host ""
Write-Host "[5/10] Accessibility/static shell contract scan"
$baseSource = Get-Content "personal_learning_assistant/ui/web/templates/base.html" -Raw
$cssSource = Get-Content "personal_learning_assistant/ui/web/static/css/app.css" -Raw
$jsSource = Get-Content "personal_learning_assistant/ui/web/static/js/app.js" -Raw
foreach ($token in @(
    'class="skip-link"',
    'id="nav-toggle"',
    'aria-controls="app-sidebar"',
    'aria-expanded="false"',
    'id="nav-backdrop"',
    'aria-current="page"',
    'aria-disabled="true"',
    'Personal Learning Intelligence'
)) {
    if (-not $baseSource.Contains($token)) { Stop-Gate "Missing shell accessibility/identity token: $token" }
}
foreach ($token in @("prefers-reduced-motion", ":focus-visible", "overflow-x: hidden")) {
    if (-not $cssSource.Contains($token)) { Stop-Gate "Missing CSS accessibility/responsive token: $token" }
}
foreach ($token in @("Escape", "aria-expanded", "nav-open")) {
    if (-not $jsSource.Contains($token)) { Stop-Gate "Missing mobile drawer behaviour token: $token" }
}
foreach ($token in @("fetch(", "XMLHttpRequest", "localStorage")) {
    if ($jsSource.Contains($token)) { Stop-Gate "Forbidden JS capability in presentation-only shell: $token" }
}
Write-Host "Accessibility/static shell contract present."

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

    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p7510_phase2_" + [guid]::NewGuid().ToString("N"))
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
        personal_learning_assistant\ui\web `
        tests\test_phase7_5_anvaya_shell.py `
        tests\test_phase7_5_web_foundation.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); c.close()"
}

Write-Host ""
Write-Host "[9/10] Protected backend/route/template hashes + forbidden-diff verification"
Assert-Hashes-Unchanged $routeBefore "Web route"
Assert-Tree-Unchanged $servicesBefore ".\personal_learning_assistant\services" "Services"
Assert-Tree-Unchanged $repositoriesBefore ".\personal_learning_assistant\repositories" "Repositories"
Assert-Tree-Unchanged $tutorBefore ".\personal_learning_assistant\tutor" "Tutor code"
Assert-Tree-Unchanged $retrievalCodeBefore ".\personal_learning_assistant\retrieval" "Retrieval code"
$templatesAfter = Hash-Tree-Except ".\personal_learning_assistant\ui\web\templates" @("base.html")
if ($templatesAfter.Count -ne $templatesBefore.Count) { Stop-Gate "Existing page template file count changed outside base.html." }
foreach ($path in $templatesBefore.Keys) {
    if (-not $templatesAfter.ContainsKey($path)) { Stop-Gate "Existing page template removed: $path" }
    if ($templatesAfter[$path] -ne $templatesBefore[$path]) { Stop-Gate "Existing page template changed outside base.html: $path" }
}

$protectedDiff = @(git diff --name-only $BaseCommit -- `
    personal_learning_assistant/ui/web/routes.py `
    personal_learning_assistant/services `
    personal_learning_assistant/repositories `
    personal_learning_assistant/tutor `
    personal_learning_assistant/retrieval)
if ($protectedDiff.Count -ne 0) { Stop-Gate "Phase 7.5.10 changed protected backend files: $($protectedDiff -join ', ')" }

Write-Host ""
Write-Host "[10/10] Scoped Git diff + production-data/retrieval-index reconciliation"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "Phase 7.5.10 gate expects no pre-staged changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.10 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\","/")
        if (-not $allowedSet.ContainsKey($normalized)) { Stop-Gate "Phase 7.5.10 changed an out-of-scope file: $normalized" }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash ".\data\learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "Phase 7.5.10 changed production SQLite." }
if ($null -ne $authorityBefore) {
    if (-not (Test-Path ".\.phase4_authority.json" -PathType Leaf)) { Stop-Gate "Phase 7.5.10 removed authority control." }
    if ((Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "Phase 7.5.10 changed authority control." }
}
foreach ($path in $legacyBefore.Keys) {
    if (-not (Test-Path $path -PathType Leaf)) { Stop-Gate "Phase 7.5.10 removed legacy JSON: $path" }
    if ((Get-FileHash $path -Algorithm SHA256).Hash -ne $legacyBefore[$path]) { Stop-Gate "Phase 7.5.10 changed legacy JSON: $path" }
}
$indexAfter = Hash-Tree ".\.phase5_retrieval"
if ($indexAfter.Count -ne $indexBefore.Count) { Stop-Gate "Phase 7.5.10 changed retrieval-index file count." }
foreach ($path in $indexBefore.Keys) {
    if (-not $indexAfter.ContainsKey($path)) { Stop-Gate "Phase 7.5.10 removed retrieval-index file: $path" }
    if ($indexAfter[$path] -ne $indexBefore[$path]) { Stop-Gate "Phase 7.5.10 changed retrieval-index file: $path" }
}

Write-Host ""
Write-Host "=================================================="
Write-Host " PHASE 7.5.10 ANVAYA PRODUCT SHELL: PASS"
Write-Host "=================================================="
Write-Host "ANVAYA shell and approved local branding are active."
Write-Host "Existing routes and backend semantics remained unchanged."
Write-Host "No new academic write capability was introduced."
Write-Host "Production academic data and retrieval indexes were unchanged by the gate."
Write-Host "Phase 7.5.10 is ready for review and the single implementation commit."
