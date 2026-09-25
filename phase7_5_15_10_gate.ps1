param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15.10/notes-obsidian-separation"
$Baseline = "2b715cf7e3310df2cd3c409387b0562645dc6858"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.10 NOTES / OBSIDIAN SEPARATION: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Notes Studio 2.0 main baseline is not an ancestor of HEAD."}

$Allowed=@(
  ".gitignore",
  "PHASE7_5_15_10_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_10_NOTES_OBSIDIAN_SEPARATION_SPEC.md",
  "personal_learning_assistant/repositories/json/anvaya_notes_repository.py",
  "personal_learning_assistant/services/anvaya_notes_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_create.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_editor.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_library.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_reader.html",
  "personal_learning_assistant/ui/web/templates/anvaya_notes_upload.html",
  "tests/test_phase7_5_15_10_notes_obsidian_separation.py",
  "phase7_5_15_10_gate.ps1"
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
  Stop-Gate "15.10 diff escaped the approved correction scope."
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
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p751510_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/10] Phase 7.5.15.10 focused separation tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_10_notes_obsidian_separation.py
}

Run-Step "[2/10] Existing Notes Studio compatibility regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py tests/test_phase7_5_15_3_full_note_reader.py tests/test_phase7_5_15_4_notes_templates.py tests/test_phase7_5_15_5_rich_visual_blocks.py tests/test_phase7_5_15_6_safe_editor_attachments.py tests/test_phase7_5_15_7_knowledge_connections.py tests/test_phase7_5_15_8_lifecycle_study_actions.py
}

Run-Step "[3/10] Legacy Notes compatibility regressions" {
  & $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py
}

Run-Step "[4/10] Obsidian product regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_study_companion.py tests/test_phase7_5_obsidian_study_repository.py
}

Run-Step "[5/10] Notes Studio final reconciliation regressions" {
  & $Py -m pytest -q tests/test_phase7_5_15_9_final_reconciliation.py tests/test_phase7_5_15_9_migration_recovery.py
}

Run-Step "[6/10] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[7/10] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[8/10] Product-separation assertions"
$nativeService=(Get-Content "personal_learning_assistant/services/anvaya_notes_service.py" -Raw).ToLowerInvariant()
$nativeRepo=(Get-Content "personal_learning_assistant/repositories/json/anvaya_notes_repository.py" -Raw).ToLowerInvariant()
foreach($token in @("obsidian_workspace_reader","build_configured_notes_studio_read_service","personal_learning_assistant.tutor")){
  if($nativeService.Contains($token) -or $nativeRepo.Contains($token)){
    Stop-Gate "Independent Notes authority depends on forbidden product boundary: $token"
  }
}

$library=Get-Content "personal_learning_assistant/ui/web/templates/anvaya_notes_library.html" -Raw
if($library.Contains("Open Obsidian workspace")){Stop-Gate "Native Notes library still links to Obsidian."}
if(-not $library.Contains("anvaya-note-card-link")){Stop-Gate "Whole-card navigation is missing."}
if(-not $library.Contains("web.anvaya_note_reader")){Stop-Gate "Native cards do not open the native full-note reader."}

$create=Get-Content "personal_learning_assistant/ui/web/templates/anvaya_notes_create.html" -Raw
foreach($label in @("Upload handwritten note","Create typed note","IRIS Academic","Preview Card","Minimal Square")){
  if(-not $create.Contains($label)){Stop-Gate "Create flow is missing: $label"}
}
if($create.Contains('name="note_date"')){Stop-Gate "Creation flow must not ask for note date."}

$routes=Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach($required in @('@web_blueprint.get("/notes/create")','@web_blueprint.post("/notes/create/typed")','@web_blueprint.post("/notes/create/upload")','@web_blueprint.get("/notes/view/<note_id>")','@web_blueprint.get("/notes/file/<note_id>/<asset_id>")')){
  if(-not $routes.Contains($required)){Stop-Gate "Native Notes route missing: $required"}
}

Write-Host ""
Write-Host "[9/10] Production authority and data protections"
Assert-Same $DataBefore (Hash-Tree ".\data") "Production data"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"
$VaultAfter=(& $Py $tmp).Trim()
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured Obsidian vault changed during Notes correction validation."}

Write-Host ""
Write-Host "[10/10] Repository hygiene"
git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.10 NOTES / OBSIDIAN SEPARATION: PASS"
Write-Host "================================================================"
Write-Host "ANVAYA Notes is an independent handwritten/typed-note library."
Write-Host "Obsidian remains a separate vault workspace; vault notes do not populate My Notes."
Write-Host "IRIS-style cards, automatic timestamps, uploads, rich typed notes and full-note navigation are green."
Write-Host "Production data, configured vault, retrieval state, Tutor code and SQLite migrations are protected."
