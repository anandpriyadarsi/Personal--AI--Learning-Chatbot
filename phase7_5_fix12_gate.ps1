param([string]$Python = "./.venv/Scripts/python.exe")

$ErrorActionPreference = "Stop"
$ExpectedBranch = "main"
$PlanPath = "docs/superpowers/plans/2026-09-19-phase7-5-12-obsidian-workspace-search.md"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "================================================================"
    Write-Host " PHASE 7.5.12 OBSIDIAN WORKSPACE + SEARCH: BLOCKED"
    Write-Host "================================================================"
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
    foreach ($item in $RelativeExcludes) {
        $excluded[$item.Replace("\","/")] = $true
    }
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

function Hash-RequiredFile {
    param([string]$Path,[string]$Label)
    if (-not (Test-Path $Path -PathType Leaf)) { Stop-Gate "$Label is missing: $Path" }
    return (Get-FileHash $Path -Algorithm SHA256).Hash
}

$PlanBaseRaw = git log -1 --format=%H -- $PlanPath
if ([string]::IsNullOrWhiteSpace($PlanBaseRaw)) {
    Stop-Gate "The Phase 7.5.12 plan must be committed separately before the implementation gate runs."
}
$BaseCommit = $PlanBaseRaw.Trim()

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
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted Phase 7.5.12 implementation on plan commit $BaseCommit but found $head."
}

$allowed = @(
    "personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py",
    "personal_learning_assistant/services/obsidian_workspace_service.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/obsidian.html",
    "personal_learning_assistant/ui/web/templates/obsidian_note.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "tests/test_phase7_5_obsidian_workspace.py",
    "tests/test_phase7_5_anvaya_shell.py",
    "PHASE7_5_FIX12_OBSIDIAN_WORKSPACE_SEARCH.md",
    "phase7_5_fix12_gate.ps1"
)
$allowedSet = @{}
foreach ($item in $allowed) { $allowedSet[$item] = $true }

foreach ($line in @(git status --porcelain=v1 -uall)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $path = $line.Substring(3).Trim().Replace("\","/")
    if ($path.Contains(" -> ")) { $path = $path.Split(" -> ")[-1] }
    if (-not $allowedSet.ContainsKey($path)) {
        Stop-Gate "Out-of-scope working-tree change: $path"
    }
}
foreach ($item in $allowed) {
    if (-not (Test-Path $item -PathType Leaf)) {
        Stop-Gate "Missing Phase 7.5.12 file: $item"
    }
}

if (-not (Test-Path "./data/learning_assistant.db" -PathType Leaf)) {
    Stop-Gate "Production SQLite database is missing."
}
if (-not (Test-Path "./.phase5_retrieval/current.json" -PathType Leaf)) {
    Stop-Gate "Current Phase 5 retrieval generation is missing."
}

$dbBefore = (Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash
$authorityExistedBefore = Test-Path "./.phase4_authority.json" -PathType Leaf
$authorityBefore = $null
if ($authorityExistedBefore) {
    $authorityBefore = (Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash
}
$legacyBefore = @{}
Get-ChildItem "./data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyBefore[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$indexBefore = Hash-Tree "./.phase5_retrieval"

$vaultHashScript = @'
import hashlib
import os
from pathlib import Path
from obsidian_integration import get_vault_path

EXCLUDED = {".obsidian", ".trash", ".git", "node_modules"}
root_value = get_vault_path()
if not root_value:
    print("SKIP")
    raise SystemExit(0)
root = Path(root_value)
if root.is_symlink() or not root.is_dir():
    print("INVALID")
    raise SystemExit(0)
digest = hashlib.sha256()
for current_root, dir_names, file_names in os.walk(str(root), topdown=True, followlinks=False):
    current = Path(current_root)
    kept = []
    for name in sorted(dir_names):
        candidate = current / name
        if name in EXCLUDED or candidate.is_symlink():
            continue
        kept.append(name)
    dir_names[:] = kept
    for name in sorted(file_names):
        if not name.lower().endswith(".md"):
            continue
        path = current / name
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
print("OK:" + digest.hexdigest())
'@
$vaultBefore = (& $PythonResolved -c $vaultHashScript).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture configured Obsidian vault Markdown hash manifest." }

$protectedObsidianIntegration = Hash-RequiredFile "./obsidian_integration.py" "Legacy Obsidian integration"
$protectedVaultScanner = Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py" "Phase 5.3 vault scanner"
$protectedVaultRegistryService = Hash-RequiredFile "./personal_learning_assistant/services/obsidian_vault_registry_service.py" "Phase 5.3 vault registry service"
$protectedVaultRepository = Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py" "Phase 5.3 vault repository"
$protectedNotesStudioService = Hash-RequiredFile "./personal_learning_assistant/services/notes_studio_service.py" "Phase 5.4 Notes Studio service"
$protectedMarkdownStore = Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/markdown_note_store.py" "Phase 5.4 Markdown store"
$protectedNotesStudioRepository = Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/notes_studio_repository.py" "Phase 5.4 Notes Studio repository"
$protectedRetrieval = Hash-Tree "./personal_learning_assistant/retrieval"
$protectedTutor = Hash-Tree "./personal_learning_assistant/tutor"
$protectedServices = Hash-Tree-Except "./personal_learning_assistant/services" @("obsidian_workspace_service.py")
$protectedFilesystemRepositories = Hash-Tree-Except "./personal_learning_assistant/repositories/filesystem" @("obsidian_workspace_reader.py")
$protectedTemplates = Hash-Tree-Except "./personal_learning_assistant/ui/web/templates" @("base.html","obsidian.html","obsidian_note.html")
$jsBefore = Hash-RequiredFile "./personal_learning_assistant/ui/web/static/js/app.js" "Web JavaScript"

Run-Step "[1/10] Phase 7.5.12 focused Obsidian workspace tests" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py
}

Run-Step "[2/10] Phase 5.3 Obsidian registry + Phase 5.4 Notes Studio regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase5_obsidian_vault_registry.py `
        tests/test_phase5_notes_studio_foundation.py
}

Run-Step "[3/10] All Phase 7.5 web regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_5_web_foundation.py `
        tests/test_phase7_5_home_dashboard.py `
        tests/test_phase7_5_courses_topics.py `
        tests/test_phase7_5_assessments.py `
        tests/test_phase7_5_progress_planning.py `
        tests/test_phase7_5_calendar_grades.py `
        tests/test_phase7_5_notes_resources.py `
        tests/test_phase7_5_operational_notes_resources.py `
        tests/test_phase7_5_knowledge_rag.py `
        tests/test_phase7_5_academic_agent_web.py `
        tests/test_phase7_5_anvaya_shell.py `
        tests/test_phase7_5_anvaya_ux_refinement.py `
        tests/test_phase7_5_obsidian_workspace.py
}

Run-Step "[4/10] Temporary-vault GET purity + traversal/symlink/XSS tests" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "read_pure or reader_preview or symlink or escapes_untrusted or non_utf8 or stale or external_change"
}

Run-Step "[5/10] Temporary-config POST connect/enable/disable + PRG tests" {
    & $PythonResolved -m pytest -q tests/test_phase7_5_obsidian_workspace.py -k "connect or enable or disable or configuration_posts or validation_error"
}

Run-Step "[6/10] Phase 7.1-7.4 regressions" {
    & $PythonResolved -m pytest -q `
        tests/test_phase7_runtime_inventory.py `
        tests/test_phase7_recovery_bundle.py `
        tests/test_phase7_restore_rehearsal.py `
        tests/test_phase7_consumer_watch.py
}

Run-Step "[7/10] Complete pytest suite" {
    $legacyNode = "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
    & $PythonResolved -m pytest -q --deselect $legacyNode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("p7512_phase2_" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path (Join-Path $temp "tests") -Force | Out-Null
        Copy-Item "./tests/test_phase2_closure_architecture.py" (Join-Path $temp "tests/test_phase2_closure_architecture.py")
        & $PythonResolved -m pytest ((Join-Path $temp "tests/test_phase2_closure_architecture.py") + "::test_phase2_root_has_no_production_learning_assistant_database") -q
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Run-Step "[8/10] Python compile + pip check + SQLite integrity/FK checks" {
    & $PythonResolved -m compileall -q `
        personal_learning_assistant/repositories/filesystem/obsidian_workspace_reader.py `
        personal_learning_assistant/services/obsidian_workspace_service.py `
        personal_learning_assistant/ui/web `
        tests/test_phase7_5_obsidian_workspace.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -c "import sqlite3; c=sqlite3.connect('file:data/learning_assistant.db?mode=ro',uri=True); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert not c.execute('PRAGMA foreign_key_check').fetchall(); c.close()"
}

Write-Host ""
Write-Host "[9/10] Protected registry/Notes-Studio/retrieval/tutor hashes + dependency scan"
if ((Hash-RequiredFile "./obsidian_integration.py" "Legacy Obsidian integration") -ne $protectedObsidianIntegration) { Stop-Gate "obsidian_integration.py changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/obsidian_vault_scanner.py" "Phase 5.3 vault scanner") -ne $protectedVaultScanner) { Stop-Gate "Phase 5.3 vault scanner changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/services/obsidian_vault_registry_service.py" "Phase 5.3 vault registry service") -ne $protectedVaultRegistryService) { Stop-Gate "Phase 5.3 vault registry service changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/obsidian_vault_repository.py" "Phase 5.3 vault repository") -ne $protectedVaultRepository) { Stop-Gate "Phase 5.3 vault repository changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/services/notes_studio_service.py" "Phase 5.4 Notes Studio service") -ne $protectedNotesStudioService) { Stop-Gate "Phase 5.4 Notes Studio service changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/filesystem/markdown_note_store.py" "Phase 5.4 Markdown store") -ne $protectedMarkdownStore) { Stop-Gate "Phase 5.4 Markdown store changed." }
if ((Hash-RequiredFile "./personal_learning_assistant/repositories/sqlite/notes_studio_repository.py" "Phase 5.4 Notes Studio repository") -ne $protectedNotesStudioRepository) { Stop-Gate "Phase 5.4 Notes Studio repository changed." }
Assert-Hash-Map-Unchanged $protectedRetrieval (Hash-Tree "./personal_learning_assistant/retrieval") "Retrieval code"
Assert-Hash-Map-Unchanged $protectedTutor (Hash-Tree "./personal_learning_assistant/tutor") "Tutor code"
Assert-Hash-Map-Unchanged $protectedServices (Hash-Tree-Except "./personal_learning_assistant/services" @("obsidian_workspace_service.py")) "Other services"
Assert-Hash-Map-Unchanged $protectedFilesystemRepositories (Hash-Tree-Except "./personal_learning_assistant/repositories/filesystem" @("obsidian_workspace_reader.py")) "Other filesystem repositories"
Assert-Hash-Map-Unchanged $protectedTemplates (Hash-Tree-Except "./personal_learning_assistant/ui/web/templates" @("base.html","obsidian.html","obsidian_note.html")) "Other web templates"
if ((Get-FileHash "./personal_learning_assistant/ui/web/static/js/app.js" -Algorithm SHA256).Hash -ne $jsBefore) { Stop-Gate "Web JavaScript changed outside Phase 7.5.12 scope." }

$routeSource = Get-Content "./personal_learning_assistant/ui/web/routes.py" -Raw
foreach ($token in @("obsidian_integration", "ObsidianVaultScanner", "SQLiteObsidianVaultRepository", "NotesStudioService", "AtomicMarkdownNoteStore", ".read_bytes(", ".read_text(")) {
    if ($routeSource.Contains($token)) { Stop-Gate "Forbidden route dependency found: $token" }
}
$serviceSource = Get-Content "./personal_learning_assistant/services/obsidian_workspace_service.py" -Raw
foreach ($token in @("obsidian_menu", "input(", "print(", "ObsidianVaultRegistryService.apply", "IndexBuilder", ".write_text(", ".write_bytes(", "os.replace(", "atomic_write(", "create_note(", "update_note(", "trash(", "restore(")) {
    if ($serviceSource.Contains($token)) { Stop-Gate "Forbidden Obsidian web-service dependency/write primitive found: $token" }
}

Write-Host ""
Write-Host "[10/10] Scoped git diff + production JSON/SQLite/retrieval/vault Markdown reconciliation"
$staged = @(git diff --cached --name-only)
if ($staged.Count -ne 0) { Stop-Gate "Phase 7.5.12 gate expects no pre-staged implementation changes." }
try {
    git add --intent-to-add -- $allowed
    if ($LASTEXITCODE -ne 0) { Stop-Gate "Unable to mark Phase 7.5.12 files intent-to-add." }
    git diff --check $BaseCommit --
    if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }
    $allChanges = @(git diff --name-only $BaseCommit --)
    foreach ($path in $allChanges) {
        $normalized = $path.Trim().Replace("\","/")
        if (-not $allowedSet.ContainsKey($normalized)) {
            Stop-Gate "Phase 7.5.12 changed an out-of-scope file: $normalized"
        }
    }
} finally {
    git reset --quiet -- $allowed 2>$null
}

if ((Get-FileHash "./data/learning_assistant.db" -Algorithm SHA256).Hash -ne $dbBefore) { Stop-Gate "Tests changed production SQLite." }
$authorityExistsAfter = Test-Path "./.phase4_authority.json" -PathType Leaf
if ($authorityExistsAfter -ne $authorityExistedBefore) {
    Stop-Gate "Tests changed authority-control file existence."
}
if ($authorityExistedBefore) {
    if ((Get-FileHash "./.phase4_authority.json" -Algorithm SHA256).Hash -ne $authorityBefore) { Stop-Gate "Tests changed authority control." }
}
$legacyAfter = @{}
Get-ChildItem "./data" -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
    $legacyAfter[$_.FullName] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
Assert-Hash-Map-Unchanged $legacyBefore $legacyAfter "Production JSON configuration"
$indexAfter = Hash-Tree "./.phase5_retrieval"
Assert-Hash-Map-Unchanged $indexBefore $indexAfter "Retrieval index"
$vaultAfter = (& $PythonResolved -c $vaultHashScript).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not recapture configured Obsidian vault Markdown hash manifest." }
if ($vaultAfter -ne $vaultBefore) { Stop-Gate "Configured Obsidian vault Markdown changed during the Phase 7.5.12 gate." }

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.12 OBSIDIAN WORKSPACE + SEARCH: PASS"
Write-Host "================================================================"
Write-Host "Obsidian connect/change, enable/disable, status, browse, lexical search, and preview are operational."
Write-Host "GET reads remained side-effect free; configuration writes remained explicit POST + 303."
Write-Host "No Markdown mutation, registry apply, Notes Studio command exposure, or retrieval-index rebuild was introduced."
Write-Host "Production academic data, JSON configuration, retrieval indexes, and configured vault Markdown were unchanged by the gate."
