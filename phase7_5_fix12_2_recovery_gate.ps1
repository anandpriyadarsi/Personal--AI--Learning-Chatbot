param(
    [string]$PythonPath = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.12.2/unified-knowledge-search"
$BaseCommit = "b89f32c4a292f9a625f91c116aa10d83b61dc905"

function Stop-Gate {
    param([string]$Message)
    Write-Host ""
    Write-Host "======================================================================="
    Write-Host " PHASE 7.5.12.2 RECOVERY: BLOCKED"
    Write-Host "======================================================================="
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

if (-not (Test-Path $PythonPath -PathType Leaf)) {
    Stop-Gate "Project virtual-environment Python was not found at $PythonPath."
}
$PythonResolved = (Resolve-Path $PythonPath).Path

$branch = (git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    Stop-Gate "Expected branch $ExpectedBranch but found $branch."
}
$head = (git rev-parse HEAD).Trim()
if ($head -ne $BaseCommit) {
    Stop-Gate "Expected uncommitted recovery on base $BaseCommit but found $head."
}

$Allowed = @(
    "PHASE7_5_12_2_RECOVERY_REPORT.md",
    "docs/superpowers/plans/2026-09-21-phase7-5-12-2-recovery.md",
    "phase7_5_fix12_2_recovery_gate.ps1",
    "personal_learning_assistant/domain/study_item_models.py",
    "personal_learning_assistant/domain/study_search_models.py",
    "personal_learning_assistant/repositories/sqlite/migrations/0007_unified_study_interactions.sql",
    "personal_learning_assistant/repositories/sqlite/study_interaction_repository.py",
    "personal_learning_assistant/repositories/sqlite/obsidian_study_repository_v2.py",
    "personal_learning_assistant/repositories/sqlite/search_metadata_repository.py",
    "personal_learning_assistant/repositories/sqlite/obsidian_study_repository.py",
    "personal_learning_assistant/services/study_interaction_service.py",
    "personal_learning_assistant/services/study_item_resolver.py",
    "personal_learning_assistant/services/unified_search_runtime.py",
    "personal_learning_assistant/services/unified_search_service.py",
    "personal_learning_assistant/services/knowledge_reader_service.py",
    "personal_learning_assistant/services/retrieval_quality_benchmark.py",
    "personal_learning_assistant/services/obsidian_study_companion_service.py",
    "personal_learning_assistant/services/academic_agent_web_service.py",
    "personal_learning_assistant/tutor/grounding.py",
    "personal_learning_assistant/ui/web/routes.py",
    "personal_learning_assistant/ui/web/templates/base.html",
    "personal_learning_assistant/ui/web/templates/knowledge.html",
    "personal_learning_assistant/ui/web/templates/knowledge_item.html",
    "personal_learning_assistant/ui/web/templates/retrieval_diagnostics.html",
    "personal_learning_assistant/ui/web/templates/_study_companion.html",
    "personal_learning_assistant/ui/web/templates/agent_session.html",
    "personal_learning_assistant/ui/web/static/css/app.css",
    "personal_learning_assistant/ui/web/static/js/app.js",
    "personal_learning_assistant/ui/web/static/js/knowledge_search.js",
    "personal_learning_assistant/ui/web/static/js/study_reader_tracker.js",
    "tests/test_phase7_5_12_2_recovery.py",
    "tests/test_phase7_5_12_2_web.py",
    "tests/test_phase7_5_month_plan_import.py"
)

# Hash production data/index/vault before any test.
$HashScript = @'
from __future__ import annotations
from pathlib import Path
import hashlib, json, sys

def hash_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def tree(root, suffix=None):
    root=Path(root)
    out={}
    if not root.exists():
        return out
    if root.is_file():
        out[str(root).replace("\\","/")]=hash_file(root)
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.suffix in {".pyc",".pyo"}:
            continue
        if suffix and p.suffix.lower()!=suffix:
            continue
        out[str(p).replace("\\","/")]=hash_file(p)
    return out

result={}
result.update(tree("data"))
result.update(tree(".phase5_retrieval"))
try:
    import obsidian_integration
    vault=obsidian_integration.get_vault_path()
    if vault:
        result.update(tree(vault, ".md"))
except Exception:
    pass
print(json.dumps(result,sort_keys=True,separators=(",",":")))
'@
$HashScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("p75122_hash_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $HashScriptPath -Value $HashScript -Encoding UTF8
$BeforeHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not capture protected hashes." }

Run-Step "[1/11] Focused Phase 7.5.12.2 recovery tests" {
    & $PythonResolved -m pytest -q `
      tests/test_phase7_5_12_2_recovery.py `
      tests/test_phase7_5_12_2_web.py
}

Run-Step "[2/11] Obsidian Reader + unified-memory compatibility" {
    & $PythonResolved -m pytest -q `
      tests/test_phase7_5_obsidian_study_repository.py `
      tests/test_phase7_5_obsidian_study_companion.py `
      tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[3/11] Retrieval + grounding + tutor regressions" {
    & $PythonResolved -m pytest -q `
      tests/test_phase5_rebuildable_retrieval.py `
      tests/test_phase6_tutor_foundation.py `
      tests/test_phase6_grounded_tutor_engine.py `
      tests/test_phase7_5_knowledge_rag.py `
      tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[4/11] Operational Planner migration compatibility" {
    & $PythonResolved -m pytest -q `
      tests/test_phase7_5_month_plan_import.py `
      tests/test_phase7_5_operational_tasks.py `
      tests/test_phase7_5_operational_calendar.py `
      tests/test_phase7_5_daily_agenda.py `
      tests/test_phase7_5_weekly_review.py
}

$Phase75Tests = @(
    Get-ChildItem -Path "tests" -Filter "test_phase7_5_*.py" -File |
    Sort-Object Name |
    ForEach-Object { $_.FullName }
)
if ($Phase75Tests.Count -eq 0) {
    Stop-Gate "No Phase 7.5 regression test files were found."
}

Run-Step "[5/11] Complete Phase 7.5 web regressions" {
    & $PythonResolved -m pytest -q @Phase75Tests
}

Run-Step "[6/11] Complete pytest regression" {
    & $PythonResolved -m pytest -q `
      --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[7/11] Python compile + pip check" {
    & $PythonResolved -m compileall -q personal_learning_assistant tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $PythonResolved -m pip check
}

# Fresh migration/integrity check through a temp Python file to avoid PowerShell quoting issues.
$FreshScript = @'
from pathlib import Path
import sqlite3, sys, tempfile
sys.path.insert(0, str(Path.cwd()))
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations

root=Path(tempfile.mkdtemp(prefix="p75122_"))
path=root/"fresh.db"
applied=apply_migrations(path)
assert applied == (1,2,3,4,5,6,7), applied
c=sqlite3.connect(path)
versions=tuple(row[0] for row in c.execute("SELECT version FROM schema_migrations ORDER BY version"))
assert versions == (1,2,3,4,5,6,7), versions
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert c.execute("PRAGMA foreign_key_check").fetchall() == []
tables={row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
assert {"study_item_reading_sessions","study_item_companion_entries"} <= tables
c.close()
print("fresh migration: PASS")
'@
$FreshScriptPath = Join-Path ([IO.Path]::GetTempPath()) ("p75122_fresh_" + [guid]::NewGuid().ToString("N") + ".py")
Set-Content -LiteralPath $FreshScriptPath -Value $FreshScript -Encoding UTF8
Run-Step "[8/11] Fresh migration 0007 + SQLite integrity/FK" {
    & $PythonResolved $FreshScriptPath
}

Write-Host ""
Write-Host "[9/11] Protected production/retrieval/vault hashes"
$AfterHashes = (& $PythonResolved $HashScriptPath).Trim()
if ($LASTEXITCODE -ne 0) { Stop-Gate "Could not re-capture protected hashes." }
if ($BeforeHashes -ne $AfterHashes) {
    Stop-Gate "Protected production data, retrieval index, configuration, or vault Markdown changed during the gate."
}

Write-Host ""
Write-Host "[10/11] Scoped diff + whitespace"
git diff --check
if ($LASTEXITCODE -ne 0) { Stop-Gate "git diff --check failed." }

$Changed = @(
    git status --porcelain=v1 -uall |
    ForEach-Object {
        $path = $_.Substring(3).Trim()
        $path = $path.Trim('"').Replace("\","/")
        $path
    }
)
$Unexpected = @($Changed | Where-Object { $_ -notin $Allowed })
if ($Unexpected.Count -gt 0) {
    Write-Host "Unexpected changed files:"
    $Unexpected | ForEach-Object { Write-Host "  $_" }
    Stop-Gate "Recovery diff escaped the approved file scope."
}

Write-Host ""
Write-Host "[11/11] Forbidden boundary scan"
$RouteText = Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach ($token in @("import sqlite3", "sqlite3.connect(", "yaml.safe_load(", "yaml.load(")) {
    if ($RouteText.Contains($token)) {
        Stop-Gate "Forbidden route-layer dependency found: $token"
    }
}

Remove-Item $HashScriptPath -Force -ErrorAction SilentlyContinue
Remove-Item $FreshScriptPath -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "======================================================================="
Write-Host " PHASE 7.5.12.2 UNIFIED KNOWLEDGE + STUDY MEMORY RECOVERY: PASS"
Write-Host "======================================================================="
Write-Host "Unified Search, stale-safe retrieval runtime, generalized study memory,"
Write-Host "Knowledge Reader/Companion, and source-scoped Ask ANVAYA are green."
Write-Host "Production data, retrieval indexes, and configured vault Markdown remained unchanged."
Write-Host "Ready for independent review and one feature-branch commit."
