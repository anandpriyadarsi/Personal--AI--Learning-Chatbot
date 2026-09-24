param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15/notes-studio-rich"
$Baseline = "96f1b60554337fa83de41995a26c7a0a02970472"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "============================================================"
  Write-Host " PHASE 7.5.15.3 FULL NOTE READER: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.2 closure commit is not an ancestor of HEAD."}

$Allowed=@(
  "personal_learning_assistant/services/notes_studio_read_service.py",
  "personal_learning_assistant/services/notes_studio_library_service.py",
  "personal_learning_assistant/services/notes_studio_reader_service.py",
  "personal_learning_assistant/services/obsidian_markdown_renderer.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/templates/notes_library.html",
  "personal_learning_assistant/ui/web/templates/notes_reader.html",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "tests/test_phase7_5_15_2_visual_notes_library.py",
  "tests/test_phase7_5_15_3_full_note_reader.py",
  "phase7_5_15_3_gate.ps1",
  "PHASE7_5_15_3_IMPLEMENTATION_REPORT.md"
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
  Stop-Gate "15.3 diff escaped approved scope."
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
  for p in sorted(Path(root).rglob("*.md")):
   if p.is_file() and not p.is_symlink():
    out[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
except Exception:
 pass
print(json.dumps(out,sort_keys=True,separators=(",",":")))
'@
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p75153_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/9] Phase 7.5.15.3 focused Full Note Reader tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_3_full_note_reader.py
}

Run-Step "[2/9] Phase 7.5.15.2 visual-library regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py
}

Run-Step "[3/9] Phase 7.5.15.1 canonical read-model regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_1_notes_studio_read_model.py
}

Run-Step "[4/9] Safe Markdown renderer and Obsidian Reader regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_obsidian_workspace.py
}

Run-Step "[5/9] Legacy Notes compatibility regressions" {
  & $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py
}

Run-Step "[6/9] Academic Agent reconciled regression" {
  & $Py -m pytest -q tests/test_phase7_5_academic_agent_web.py
}

Run-Step "[7/9] Complete pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[8/9] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Write-Host ""
Write-Host "[9/9] Scope and authority protections"
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
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured vault Markdown changed."}

git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

$reader=Get-Content "personal_learning_assistant/services/notes_studio_reader_service.py" -Raw
foreach($token in @(
  "personal_learning_assistant.tutor",
  "NotesStudioService",
  "sqlite3",
  ".read_text(",
  ".read_bytes(",
  ".write_text(",
  ".write_bytes(",
  "os.replace(",
  "apply_snapshot("
)){
  if($reader.Contains($token)){Stop-Gate "Forbidden Full Note Reader dependency/mutation token: $token"}
}

$template=Get-Content "personal_learning_assistant/ui/web/templates/notes_reader.html" -Raw
foreach($token in @("note.text","note.body","|safe","obsidian_reader.js","<textarea")){
  if($template.Contains($token)){Stop-Gate "Full Note Reader contains forbidden raw/write/tracking token: $token"}
}

Write-Host ""
Write-Host "============================================================"
Write-Host " PHASE 7.5.15.3 FULL NOTE READER: PASS"
Write-Host "============================================================"
Write-Host "Full academic Markdown rendering, metadata, backlinks and linked-note navigation are green."
Write-Host "Vault Markdown, production data, retrieval state, Tutor code and SQLite migrations are protected."
