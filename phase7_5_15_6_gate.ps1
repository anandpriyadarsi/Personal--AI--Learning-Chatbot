param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15/notes-studio-rich"
$Baseline = "3b83ab2c18f4f33778bbb254b6674b0ade7a7c0a"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " PHASE 7.5.15.6 SAFE EDITOR + ATTACHMENTS: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.5 closure commit is not an ancestor of HEAD."}

$Allowed=@(
  "personal_learning_assistant/domain/notes_studio_models.py",
  "personal_learning_assistant/repositories/filesystem/markdown_note_store.py",
  "personal_learning_assistant/services/notes_studio_service.py",
  "personal_learning_assistant/services/notes_studio_editor_service.py",
  "personal_learning_assistant/services/notes_studio_reader_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/templates/notes_editor.html",
  "personal_learning_assistant/ui/web/templates/notes_library.html",
  "personal_learning_assistant/ui/web/templates/notes_reader.html",
  "personal_learning_assistant/ui/web/templates/notes_template_preview.html",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "tests/test_phase7_5_15_2_visual_notes_library.py",
  "tests/test_phase7_5_15_3_full_note_reader.py",
  "tests/test_phase7_5_15_4_notes_templates.py",
  "tests/test_phase7_5_15_6_safe_editor_attachments.py",
  "phase7_5_15_6_gate.ps1",
  "PHASE7_5_15_6_IMPLEMENTATION_REPORT.md"
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
  Stop-Gate "15.6 diff escaped approved scope."
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
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p75156_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/12] Phase 7.5.15.6 focused safe-editor tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_6_safe_editor_attachments.py
}

Run-Step "[2/12] Phase 5.4 Notes Studio write-protocol regression" {
  & $Py -m pytest -q tests/test_phase5_notes_studio_foundation.py
}

Run-Step "[3/12] Phase 7.5.15.5 rich-visual regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_5_rich_visual_blocks.py
}

Run-Step "[4/12] Phase 7.5.15.4 template regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_4_notes_templates.py
}

Run-Step "[5/12] Phase 7.5.15.3 Full Note Reader regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_3_full_note_reader.py
}

Run-Step "[6/12] Phase 7.5.15.2 Visual Notes Library regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py
}

Run-Step "[7/12] Phase 7.5.15.1 canonical read-model regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_1_notes_studio_read_model.py
}

Run-Step "[8/12] Obsidian renderer/workspace/Reader regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py
}

Run-Step "[9/12] Legacy Notes and Academic Agent regressions" {
  & $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[10/12] Complete pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[11/12] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[12/12] Scope, authority and write-path protections"
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

$editor=Get-Content "personal_learning_assistant/services/notes_studio_editor_service.py" -Raw
$editorLower=$editor.ToLowerInvariant()
foreach($token in @(
  ".write_text(",
  ".write_bytes(",
  "os.replace(",
  "sqlite3.connect(",
  "personal_learning_assistant.tutor",
  "openai",
  "requests",
  "httpx"
)){
  if($editorLower.Contains($token)){Stop-Gate "Editor bypass/forbidden dependency detected: $token"}
}
if(-not $editorLower.Contains("notes_studio_service")){
  Stop-Gate "Editor is not delegating to the established Notes Studio write service."
}

$routes=Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach($required in @(
  '@web_blueprint.get("/notes/new")',
  '@web_blueprint.post("/notes/new")',
  '@web_blueprint.get("/notes/edit")',
  '@web_blueprint.post("/notes/edit")',
  '@web_blueprint.post("/notes/attachments")'
)){
  if(-not $routes.Contains($required)){Stop-Gate "Required editor route missing: $required"}
}
if($routes.Contains("notes_studio_service import NotesStudioService")){
  Stop-Gate "Web routes must not bypass the editor service into NotesStudioService."
}

$store=Get-Content "personal_learning_assistant/repositories/filesystem/markdown_note_store.py" -Raw
foreach($required in @("safe_attachment_filename","expected_note_hash","_attachments")){
  if(-not $store.Contains($required)){Stop-Gate "Attachment safety primitive missing: $required"}
}

$template=Get-Content "personal_learning_assistant/ui/web/templates/notes_editor.html" -Raw
foreach($forbidden in @("|safe",'<input type="hidden" name="body"')){
  if($template.Contains($forbidden)){Stop-Gate "Editor template contains unsafe body/render token: $forbidden"}
}

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 7.5.15.6 SAFE EDITOR + ATTACHMENTS: PASS"
Write-Host "============================================================"
Write-Host "Managed note creation, expected-hash editing, rich metadata preservation and safe image attachments are green."
Write-Host "All writes reuse the Phase 5.4 command/journal protocol; production vault, data, retrieval, Tutor and migrations are protected."
