param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15.11/inline-note-media"
$Baseline = "efd5bbb00e9d4561051b2baa0d3608fc3f79f31e"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.11 INLINE NOTE MEDIA + ZIP IMPORT: BLOCKED"
  Write-Host "================================================================"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Green Phase 7.5.15.10 baseline is not an ancestor of HEAD."}

$Allowed=@(
  "PHASE7_5_15_11_INLINE_NOTE_MEDIA_SPEC.md",
  "PHASE7_5_15_11_IMPLEMENTATION_REPORT.md",
  "personal_learning_assistant/repositories/json/anvaya_notes_repository.py",
  "personal_learning_assistant/services/anvaya_notes_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_upload.html",
  "tests/test_phase7_5_15_11_inline_note_media.py",
  "phase7_5_15_11_gate.ps1"
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
  Stop-Gate "15.11 diff escaped the approved inline-media scope."
}

$DataBefore=Hash-Tree ".\data"
$RetrievalBefore=Hash-Tree ".\.phase5_retrieval"
$TutorBefore=Hash-Tree ".\personal_learning_assistant\tutor"
$MigrationsBefore=Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations"

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
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p751511_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/11] Phase 7.5.15.11 focused inline-media tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_11_inline_note_media.py
}

Run-Step "[2/11] Phase 7.5.15.10 Notes/Obsidian separation regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_10_notes_obsidian_separation.py
}

Run-Step "[3/11] Rich Notes editor/reader regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_3_full_note_reader.py tests/test_phase7_5_15_5_rich_visual_blocks.py tests/test_phase7_5_15_6_safe_editor_attachments.py
}

Run-Step "[4/11] Notes library/lifecycle regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py tests/test_phase7_5_15_4_notes_templates.py tests/test_phase7_5_15_7_knowledge_connections.py tests/test_phase7_5_15_8_lifecycle_study_actions.py
}

Run-Step "[5/11] Legacy Notes compatibility regressions" {
  & $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py
}

Run-Step "[6/11] Obsidian independence regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_obsidian_study_repository.py
}

Run-Step "[7/11] Final Notes reconciliation regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_9_final_reconciliation.py tests/test_phase7_5_15_9_migration_recovery.py
}

Run-Step "[8/11] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[9/11] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[10/11] Inline-media safety and authority assertions"
$service=(Get-Content "personal_learning_assistant/services/anvaya_notes_service.py" -Raw).ToLowerInvariant()
foreach($token in @("obsidian_workspace_reader","personal_learning_assistant.tutor")){
  if($service.Contains($token)){Stop-Gate "Inline Notes service crossed a forbidden authority boundary: $token"}
}
foreach($required in @("zipfile","anvaya-upload:","anvaya-image:","max_expanded_bytes","_render_typed_body")){
  if(-not $service.Contains($required)){Stop-Gate "Inline-media service is missing required safety/placement behavior: $required"}
}
$editor=Get-Content "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html" -Raw
foreach($required in @("Insert at cursor","Insert ZIP images here","data-media-width","data-media-rotate","data-media-crop",".zip")){
  if(-not $editor.Contains($required)){Stop-Gate "Editor media control missing: $required"}
}
$css=Get-Content "personal_learning_assistant/ui/web/static/css/app.css" -Raw
foreach($required in @(".anvaya-inline-media",".anvaya-media-width-70",".anvaya-media-rotate-90",".anvaya-media-crop-1x1")){
  if(-not $css.Contains($required)){Stop-Gate "Inline media presentation CSS missing: $required"}
}

Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"
$VaultAfter=(& $Py $tmp).Trim()
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured Obsidian vault changed during inline-media validation."}

Write-Host ""
Write-Host "[11/11] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.11 INLINE NOTE MEDIA + ZIP IMPORT: PASS"
Write-Host "================================================================"
Write-Host "Multiple images and safe ZIP batches are supported inside independent ANVAYA Notes."
Write-Host "Typed-note images can render between text with bounded size, rotation, crop and caption settings."
Write-Host "Original image bytes are preserved; inline media is not duplicated at the attachment footer."
Write-Host "Obsidian, Tutor, production data, retrieval state and SQLite migrations remain protected."
