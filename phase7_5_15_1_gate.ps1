param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15/notes-studio-rich"
$AuditCommit = "7c0ada081976252485131e0ccf863b5c6d48de7e"

function Stop-Gate { param([string]$Message)
  Write-Host ""; Write-Host "============================================================"
  Write-Host " PHASE 7.5.15.1 CANONICAL NOTES READ MODEL: BLOCKED"
  Write-Host "============================================================"; Write-Host $Message; exit 1
}
function Run-Step { param([string]$Label,[scriptblock]$Command)
  Write-Host ""; Write-Host $Label; & $Command
  if($LASTEXITCODE -ne 0){ Stop-Gate "$Label failed with exit code $LASTEXITCODE." }
}
function Hash-Tree { param([string]$Root)
  $out=@{}; if(Test-Path $Root){
    Get-ChildItem $Root -File -Recurse -Force |
      Where-Object {$_.Extension -notin @(".pyc",".pyo") -and $_.FullName -notmatch '[\\/]__pycache__[\\/]'} |
      Sort-Object FullName | ForEach-Object {$out[$_.FullName]=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
  }; return $out
}
function Assert-Same { param([hashtable]$Before,[hashtable]$After,[string]$Label)
  if($Before.Count -ne $After.Count){Stop-Gate "$Label file count changed."}
  foreach($p in $Before.Keys){
    if(-not $After.ContainsKey($p)){Stop-Gate "$Label removed file: $p"}
    if($Before[$p] -ne $After[$p]){Stop-Gate "$Label changed file: $p"}
  }
}

if(Test-Path $Python){$Py=(Resolve-Path $Python).Path}else{$cmd=Get-Command $Python -ErrorAction SilentlyContinue;if($null -eq $cmd){Stop-Gate "Python not found."};$Py=$cmd.Source}
$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}
git merge-base --is-ancestor $AuditCommit HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "15.1 pre-edit audit commit is not an ancestor of HEAD."}

$Allowed=@(
 "PHASE7_5_15_1_PRE_EDIT_AUDIT.md",
 "personal_learning_assistant/domain/notes_studio_read_models.py",
 "personal_learning_assistant/services/notes_studio_read_service.py",
 "tests/test_phase7_5_15_1_notes_studio_read_model.py",
 "tests/test_phase7_5_academic_agent_web.py",
 "phase7_5_15_1_gate.ps1",
 "PHASE7_5_15_1_IMPLEMENTATION_REPORT.md"
)
$changed=@(git diff --name-only "${AuditCommit}..HEAD"; git status --porcelain=v1 -uall | ForEach-Object {$_.Substring(3).Trim().Replace("\","/")})
$unexpected=@($changed | Where-Object {$_ -and $_ -notin $Allowed} | Sort-Object -Unique)
if($unexpected.Count){$unexpected|ForEach-Object{Write-Host "Unexpected: $_"};Stop-Gate "15.1 diff escaped approved scope."}

$DataBefore=Hash-Tree ".\data"
$RetrievalBefore=Hash-Tree ".\.phase5_retrieval"
$TutorBefore=Hash-Tree ".\personal_learning_assistant\tutor"
$MigrationsBefore=Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations"
$AuthorityBefore=$null;if(Test-Path ".\.phase4_authority.json"){$AuthorityBefore=(Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash}

$VaultHashScript=@'
from pathlib import Path
import hashlib, json
out={}
try:
 import obsidian_integration
 root=obsidian_integration.get_vault_path()
 if root and Path(root).is_dir():
  for p in sorted(Path(root).rglob("*.md")):
   if p.is_file() and not p.is_symlink():
    out[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
except Exception:
 pass
print(json.dumps(out,sort_keys=True,separators=(",",":")))
'@
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p75151_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/7] Phase 7.5.15.1 focused read-model tests" {& $Py -m pytest -q tests/test_phase7_5_15_1_notes_studio_read_model.py}
Run-Step "[2/7] Phase 5.4 Notes Studio foundation regression" {& $Py -m pytest -q tests/test_phase5_notes_studio_foundation.py}
Run-Step "[3/7] Obsidian reader/workspace regressions" {& $Py -m pytest -q tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_obsidian_study_repository.py}
Run-Step "[4/7] Legacy Notes compatibility regressions" {& $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py tests/test_phase2_notes_service.py tests/test_phase2_notes_write_adapter.py}
Run-Step "[5/7] Unified knowledge/live UX regressions" {& $Py -m pytest -q tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_12_2_web.py tests/test_phase7_5_12_3_live_ux_fix.py}
Run-Step "[6/7] Complete suite + compile + pip check" {
 & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
 & $Py -m compileall -q personal_learning_assistant tests
 if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
 & $Py -m pip check
}

Write-Host "";Write-Host "[7/7] Authority, Tutor, retrieval, vault and scoped-diff protections"
Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"
if($AuthorityBefore -and (Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash -ne $AuthorityBefore){Stop-Gate "Authority control changed."}
$VaultAfter=(& $Py $tmp).Trim();if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured vault Markdown changed."}
Remove-Item $tmp -Force -ErrorAction SilentlyContinue

git diff --check "${AuditCommit}..HEAD"
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}
$source=Get-Content "personal_learning_assistant/services/notes_studio_read_service.py" -Raw
foreach($token in @("personal_learning_assistant.tutor","NotesStudioService","KnowledgeReaderService","LegacyJsonNoteRepository","sqlite3","write_text(","write_bytes(","os.replace(","apply_snapshot(")){
 if($source.Contains($token)){Stop-Gate "Forbidden read-service dependency/mutation token: $token"}
}

Write-Host "";Write-Host "============================================================"
Write-Host " PHASE 7.5.15.1 CANONICAL NOTES READ MODEL: PASS"
Write-Host "============================================================"
Write-Host "NoteCard/NoteDetail and the canonical read-only service are green."
Write-Host "Legacy Notes, Tutor, SQLite migrations, retrieval state and vault Markdown are protected."


