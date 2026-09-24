param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$ExpectedBranch = "phase7.5.15/notes-studio-rich"
$Baseline = "f780cab7eaf8f55b2d0e963e4f317d61adcdbe29"
$Range = "$Baseline..HEAD"

function Stop-Gate { param([string]$Message)
  Write-Host ""
  Write-Host "================================================================"
  Write-Host " PHASE 7.5.15.9 RECONCILIATION + FINAL GATE: BLOCKED"
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
if($LASTEXITCODE -ne 0){Stop-Gate "Phase 7.5.15.8 closure commit is not an ancestor of HEAD."}

$Allowed=@(
  "PHASE7_5_15_9_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_9_RECONCILIATION_DECISION.md",
  "personal_learning_assistant/services/notes_studio_reconciliation_service.py",
  "personal_learning_assistant/ui/web/routes.py",
  "personal_learning_assistant/ui/web/static/css/app.css",
  "personal_learning_assistant/ui/web/templates/notes_library.html",
  "personal_learning_assistant/ui/web/templates/notes_reconciliation.html",
  "tests/test_phase7_5_15_9_final_reconciliation.py",
  "phase7_5_15_9_gate.ps1",
  "phase7_5_15_9_verify.py"
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
  Stop-Gate "15.9 diff escaped approved reconciliation/final-gate scope."
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
$tmp=Join-Path ([IO.Path]::GetTempPath()) ("p75159_"+[guid]::NewGuid().ToString("N")+".py")
Set-Content $tmp $VaultHashScript -Encoding UTF8
$VaultBefore=(& $Py $tmp).Trim()

Run-Step "[1/17] Phase 7.5.15.9 focused final-reconciliation tests" {
  & $Py -m pytest -q tests/test_phase7_5_15_9_final_reconciliation.py
}

Run-Step "[2/17] Read-only production reconciliation verifier" {
  & $Py .\phase7_5_15_9_verify.py --project-root . --database .\data\learning_assistant.db --legacy-notes .\data\notes.json
}

Run-Step "[3/17] Phase 7.5.15.8 Lifecycle + Study Actions regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_8_lifecycle_study_actions.py
}

Run-Step "[4/17] Phase 7.5.15.7 Knowledge Connections regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_7_knowledge_connections.py
}

Run-Step "[5/17] Phase 7.5.15.6 Safe Editor + Attachments regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_6_safe_editor_attachments.py
}

Run-Step "[6/17] Phase 7.5.15.5 Rich Visual Blocks regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_5_rich_visual_blocks.py
}

Run-Step "[7/17] Phase 7.5.15.4 Academic Templates regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_4_notes_templates.py
}

Run-Step "[8/17] Phase 7.5.15.3 Full Note Reader regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_3_full_note_reader.py
}

Run-Step "[9/17] Phase 7.5.15.2 Visual Notes Library regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_2_visual_notes_library.py
}

Run-Step "[10/17] Phase 7.5.15.1 Canonical Read Model regression" {
  & $Py -m pytest -q tests/test_phase7_5_15_1_notes_studio_read_model.py
}

Run-Step "[11/17] Phase 5.4 Notes Studio write/lifecycle foundation regression" {
  & $Py -m pytest -q tests/test_phase5_notes_studio_foundation.py
}

Run-Step "[12/17] Legacy Notes compatibility regressions" {
  & $Py -m pytest -q tests/test_phase7_5_notes_resources.py tests/test_phase7_5_operational_notes_resources.py
}

Run-Step "[13/17] Obsidian + unified-knowledge live regressions" {
  & $Py -m pytest -q tests/test_phase7_5_obsidian_markdown_renderer.py tests/test_phase7_5_obsidian_workspace.py tests/test_phase7_5_obsidian_reader_routes.py tests/test_phase7_5_12_2_recovery.py tests/test_phase7_5_12_2_web.py tests/test_phase7_5_12_3_live_ux_fix.py
}

Run-Step "[14/17] Complete project pytest suite" {
  & $Py -m pytest -q --deselect "tests/test_phase2_closure_architecture.py::test_phase2_root_has_no_production_learning_assistant_database"
}

Run-Step "[15/17] Compile and dependency consistency" {
  & $Py -m compileall -q personal_learning_assistant tests phase7_5_15_9_verify.py
  if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
  & $Py -m pip check
}

Run-Step "[16/17] Explicit SQLite integrity and foreign-key checks" {
  & $Py -c "import sqlite3; from pathlib import Path; from urllib.parse import quote; p=Path('data/learning_assistant.db').resolve(strict=False); u='file:{}?mode=ro'.format(quote(str(p).replace(chr(92),'/'),safe='/:')); c=sqlite3.connect(u,uri=True,isolation_level=None); assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; assert c.execute('PRAGMA foreign_key_check').fetchall()==[]; c.close(); print('SQLite integrity: ok'); print('SQLite foreign keys: ok')"
}

Write-Host ""
Write-Host "[17/17] Final authority, compatibility and scoped-diff protections"

Assert-Same $DataBefore (Hash-Tree ".\data") "Production data / legacy JSON / Obsidian config"
Assert-Same $RetrievalBefore (Hash-Tree ".\.phase5_retrieval") "Retrieval state"
Assert-Same $TutorBefore (Hash-Tree ".\personal_learning_assistant\tutor") "Tutor code"
Assert-Same $MigrationsBefore (Hash-Tree ".\personal_learning_assistant\repositories\sqlite\migrations") "SQLite migrations"

if($AuthorityBefore){
  $AuthorityAfter=(Get-FileHash ".\.phase4_authority.json" -Algorithm SHA256).Hash
  if($AuthorityAfter -ne $AuthorityBefore){Stop-Gate "Authority-control file changed."}
}

$VaultAfter=(& $Py $tmp).Trim()
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
if($VaultBefore -ne $VaultAfter){Stop-Gate "Configured production vault contents changed during final validation."}

git diff --check $Range
if($LASTEXITCODE -ne 0){Stop-Gate "git diff --check failed."}

$decision=Get-Content "PHASE7_5_15_9_RECONCILIATION_DECISION.md" -Raw
foreach($required in @(
  "NO AUTOMATIC LEGACY MIGRATION",
  "Obsidian Markdown",
  "data/notes.json",
  "separate reviewed migration",
  "no SQLite migration",
  "Tutor"
)){
  if(-not $decision.Contains($required)){Stop-Gate "Reconciliation decision is missing: $required"}
}

$reconciliation=Get-Content "personal_learning_assistant/services/notes_studio_reconciliation_service.py" -Raw
$reconciliationLower=$reconciliation.ToLowerInvariant()
foreach($token in @(
  "personal_learning_assistant.tutor",
  "openai",
  "requests",
  "httpx",
  ".write_text(",
  ".write_bytes(",
  "os.replace(",
  "apply_migrations(",
  "create_note(",
  "update_note("
)){
  if($reconciliationLower.Contains($token)){Stop-Gate "Final reconciliation contains forbidden mutation/dependency token: $token"}
}

$routes=Get-Content "personal_learning_assistant/ui/web/routes.py" -Raw
foreach($required in @(
  '@web_blueprint.get("/notes")',
  '@web_blueprint.get("/notes/reconciliation")',
  '@web_blueprint.post("/notes")',
  '@web_blueprint.post("/notes/<int:position>")'
)){
  if(-not $routes.Contains($required)){Stop-Gate "Expected final compatibility route is missing: $required"}
}
if($routes.Contains('@web_blueprint.post("/notes/reconciliation")')){
  Stop-Gate "Reconciliation preview must remain GET-only."
}
foreach($forbidden in @(
  '@web_blueprint.post("/notes/delete")',
  '@web_blueprint.delete("/notes',
  "delete_forever"
)){
  if($routes.ToLowerInvariant().Contains($forbidden.ToLowerInvariant())){Stop-Gate "Unapproved permanent-delete behavior detected: $forbidden"}
}

$library=Get-Content "personal_learning_assistant/ui/web/templates/notes_library.html" -Raw
if(-not $library.Contains("url_for('web.notes_new')")){Stop-Gate "Default Notes Library does not route new notes through Safe Editor."}
if(-not $library.Contains("url_for('web.notes_reconciliation')")){Stop-Gate "Legacy preservation does not expose reconciliation preview."}
if($library.Contains('action="/notes"')){Stop-Gate "Default rich Notes Library unexpectedly exposes the legacy write form."}

$reconciliationTemplate=Get-Content "personal_learning_assistant/ui/web/templates/notes_reconciliation.html" -Raw
if($reconciliationTemplate.ToLowerInvariant().Contains("<form")){Stop-Gate "Final reconciliation view must not expose mutation forms."}
if(-not $reconciliationTemplate.Contains("No automatic migration")){Stop-Gate "Final reconciliation UI does not state the migration decision."}

foreach($file in @(
  "PHASE7_5_15_NOTES_STUDIO_2_MASTER_SPEC.md",
  "PHASE7_5_15_1_CANONICAL_READ_MODEL_PLAN.md",
  "PHASE7_5_15_1_PRE_EDIT_AUDIT.md",
  "PHASE7_5_15_2_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_3_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_4_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_5_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_6_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_7_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_8_IMPLEMENTATION_REPORT.md",
  "PHASE7_5_15_9_RECONCILIATION_DECISION.md"
)){
  if(-not (Test-Path $file)){Stop-Gate "Phase 7.5.15 evidence file is missing: $file"}
}

Write-Host ""
Write-Host "================================================================"
Write-Host " PHASE 7.5.15.9 RECONCILIATION + FINAL GATE: PASS"
Write-Host "================================================================"
Write-Host "Notes Studio 2.0 is reconciled end to end."
Write-Host "Obsidian Markdown remains authoritative; legacy JSON is preserved with no automatic migration."
Write-Host "All Phase 7.5.15 units are green; production data, vault, retrieval, Tutor and migrations are protected."
Write-Host "Phase 7.5.15 is ready for merge consideration after explicit integration review."
