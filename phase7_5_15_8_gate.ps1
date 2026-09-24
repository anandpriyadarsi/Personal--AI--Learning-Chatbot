param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15/notes-studio-rich"
$Baseline = "a43d12e564a80bb2dbabb738ad10645121b3ccb5"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " PHASE 7.5.15.8 LIFECYCLE + STUDY ACTIONS: BLOCKED"
  Write-Host "============================================================"
  Write-Host $Message
  exit 1
}

function Run-Step { param([string]$Label,[scriptblock]$Command)
  Write-Host ""
  Write-Host $Label
  & $Command
  if($LASTEXITCODE -ne 0){ Stop-Gate "$Label failed with exit code $LASTEXITCODE." }
}

function Hash-Tree { param([string]$Root)
  $out=@{}
  if(Test-Path $Root){
    Get-ChildItem $Root -File -Recurse -Force |
      Where-Object {$_.Extension -notin @(".pyc",".pyo") -and $_.FullName -notmatch '[\\/]__pycache__[\\/]'} |
      Sort-Object FullName |
      ForEach-Object {$out[$_.FullName]=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}
  }
  return $out
}

function Assert-Same { param([hashtable]$Before,[hashtable]$After,[string]$Label)
  if($Before.Count -ne $After.Count){Stop-Gate "$Label file count changed."}
  foreach($p in $Before.Keys){
    if(-not $After.ContainsKey($p)){Stop-Gate "$Label removed file: $p"}
    if($Before[$p] -ne $After[$p]){Stop-Gate "$Label changed file: $p"}
  }
}

if(Test-Path $Python){
  $Py=(Resolve-Path $Python).Path
}else{
  $cmd=Get-Command $Python -ErrorAction SilentlyContinue
  if($null -eq $cmd){Stop-Gate "Python not found."}
  $Py=$cmd.Source
}

$branch=(git branch --show-current).Trim()
if($branch -ne $ExpectedBranch){Stop-Gate "Expected $ExpectedBranch but found $branch."}

git merge-base --is-ancestor $Baseline HEAD | Out-Null
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.7 closure commit is not an ancestor of HEAD."}

$Allowed=@(
  "personal_learning_assistant/domain/notes_studio_read_models.py",
  "personal_learning_assistant/repositories/sqlite/notes_studio_repository.py",
  "personal_learning_assistant/services/notes_studio_library_service.py",
  "personal_learning_assistant/services/notes_studio_lifecycle_service.py",
  "personal_learning_assistant/services/notes_studio_read_service.py",
  "personal_learning_assistant/services/notes_studio_reader_service.py",
  "personal_learning_assistant/services/notes_studio_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/notes_library.html",
  "personal_learning_assistant/ui/web/templates/notes_reader.html",
  "personal_learning_assistant/ui/web/templates/notes_trash.html",
  "tests/test_phase7_5_15_2_visual_notes_library.py",
  "tests/test_phase7_5_15_8_lifecycle_study_actions.py",
  "phase7_5_15_8_gate.ps1",
  "PHASE7_5_15_8_IMPLEMENTATION_REPORT.md"
)

$changed=@(
  git diff --name-only $Range
  git status --porcelain=v1 -uall | ForEach-Object {
    if($_.Length -ge 4){$_.Substring(3).Trim().Replace("\","/")}
  }
)
$unexpected=@($changed | Where-Object {$_ -and $_ -notin $Allowed} | Sort-Object -Unique)
if($unexpected.Count){
  $unexpected | ForEach-Object {Write-Host "Unexpected: $_"}
  Stop-Gate "15.8 diff escaped approved scope."
}

$DataBefore=Hash-Tree ".\data"
$RetrievalBefore=Hash-Tree ".\.phase5_retrieval"
$TutorBefore=Hash-Tree ".\personal_learning_assistant\tutor"
$MigrationsBefore=Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations"
$AuthorityBefore=$null
if(Test-Path ".\.phase4_authority.json"){
  $AuthorityBefore=(Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
}

$VaultHashScript=@'
from pathlib import Path
import hashlib, json
out={}
try:
 import obsidian_integration
 cfg=obsidian_integration.load_config()
 root=(cfg or {}).get("vault_path","") if isinstance(cfg,dict) else ""
 if root and Path(root).is_dir():
  for p in sorted(Path(root).rglob("*")):
   if p.is_file() and not p.is_symlink():
    out[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
except Exception:
 pass
print(json.dumps(out,sort_keys=True,separators=(",",":")))
'@
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p75158_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/13] Phase 7.5.15.8 focused lifecycle/study-action tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_8_lifecycle_study_actions.py
}

Run-Step "[2/13] Phase 5.4 lifecycle/write-protocol regression" {
  & $Py -m pytest -q tests/test_phase5_notes_studio_foundation.py
}

Run-Step "[3/13] Phase 7.5.15.7 Knowledge Connections regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_7_knowledge_connections.py
}

Run-Step "[4/13] Phase 7.5.15.6 Safe Editor regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_6_safe_editor_attachments.py
}

Run-Step "[5/13] Phase 7.5.15.5 Rich Visual Blocks regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_5_rich_visual_blocks.py
}

Run-Step "[6/13] Phase 7.5.15.4 Templates regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_4_notes_templates.py
}

Run-Step "[7/13] Phase 7.5.15.3 Full Note Reader regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_3_full_note_reader.py
}

Run-Step "[8/13] Phase 7.5.15.2 Visual Notes Library regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py
}

Run-Step "[9/13] Phase 7.5.15.1 canonical read-model regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_1_notes_studio_read_model.py
}

Run-Step "[10/13] Obsidian renderer/workspace/Reader regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[11/13] Complete pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[12/13] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[13/13] Authority, lifecycle and scoped-diff protections"
Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"
if($AuthorityBefore){
  $AuthorityAfter=(Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
  if($AuthorityAfter -ne $AuthorityBefore){Stop-Gate "Authority control changed."}
}
$VaultAfter=(& $Py $tmp).Trim()
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured production vault contents changed during gate execution."}

git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

$lifecycle=Get-Content "personal_learning_assistant/services/notes_studio_lifecycle_service.py" -Raw
$lifecycleLower=$lifecycle.ToLowerInvariant()
foreach($token in @(
  "personal_learning_assistant.tutor",
  "openai",
  "requests",
  "httpx",
  ".write_text(",
  ".write_bytes(",
  "os.replace("
)){
  if($lifecycleLower.Contains($token)){Stop-Gate "Forbidden lifecycle dependency/write bypass: $token"}
}
if(-not $lifecycle.Contains("configured_notes_studio_mutation_context")){
  Stop-Gate "Lifecycle writes are not reusing the established Notes Studio mutation context."
}

$routes=Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach($required in @(
  '@web_blueprint.post("/notes/lifecycle")',
  '@web_blueprint.get("/notes/trash")',
  '@web_blueprint.post("/notes/restore")'
)){
  if(-not $routes.Contains($required)){Stop-Gate "Required lifecycle route missing: $required"}
}
foreach($forbidden in @(
  '@web_blueprint.post("/notes/delete")',
  '@web_blueprint.delete("/notes',
  "delete_forever"
)){
  if($routes.ToLowerInvariant().Contains($forbidden.ToLowerInvariant())){
    Stop-Gate "Unapproved permanent-delete behavior detected: $forbidden"
  }
}

$readerTemplate=Get-Content "personal_learning_assistant/ui/web/templates/notes_reader.html" -Raw
foreach($required in @(
  "Pin note",
  "Archive note",
  "Move to trash",
  "Needs practice",
  "Review due",
  "Mastered"
)){
  if(-not $readerTemplate.Contains($required)){Stop-Gate "Reader lifecycle/study action missing: $required"}
}

$trashTemplate=Get-Content "personal_learning_assistant/ui/web/templates/notes_trash.html" -Raw
if(-not $trashTemplate.Contains('name="relative_path"')){
  Stop-Gate "Trash restore does not require an explicit destination."
}
if(($readerTemplate + $trashTemplate).ToLowerInvariant().Contains("delete forever")){
  Stop-Gate "Permanent-delete UI is not approved."
}

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 7.5.15.8 LIFECYCLE + STUDY ACTIONS: PASS"
Write-Host "============================================================"
Write-Host "Pin/unpin, archive/unarchive, trash/restore and bounded study-status actions are green."
Write-Host "Lifecycle authority stays in SQLite; file moves/status writes reuse Phase 5.4 safety; Tutor, retrieval and migrations are protected."
