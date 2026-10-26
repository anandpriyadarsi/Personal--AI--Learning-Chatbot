# Independent final-handoff draft preflight

Review date: 2026-10-14. Scope: proposed document text and targeted replacements in `b3-evidence/finalize_reports.py`, current handoff/implementation/recovery documents, and the available preservation/local/policy evidence summaries. Reviewed generator SHA-256: `3f44421ebb2d0dc88570a141ccc098fb4a2b76fba6d969d01ad85ba2db709889`. No broad architecture or implementation audit. The generator was read and syntax-parsed, **not executed**. No source or delivery document was edited.

The proposed final report assumes exact-source acceptance for `63c5a636f4e737c204a791360e2bc715c9ac945f`, run `38525732263`. At this preflight the corresponding `b3-ci/scope/source-parity.json` does not exist. All proposed PASS text is therefore reviewed as conditional draft text, not independently accepted CI results.

## Disposition: one Important finding, corrected in the draft generator

### H1 — Important: implementation-report evidence-preservation claims survive despite known loss

The generator replaces the automated validation report with an appropriately candid recovery account, but its implementation-report replacements (approximately lines 49–54) leave this sentence unchanged:

> The first full B3 attempt found43 setup errors from a missing ephemeral Chromium executable, with zero assertion failures; retained as failed evidence, followed by a fresh runtime installation and complete rerun.

The currently tracked `WORKSPACE_RECOVERY.md` explicitly says the original missing-browser 43-setup-error log and original local accepted-1961 records were removed before an archive was saved. Thus “retained as failed evidence” misleadingly implies the original failed-run evidence still exists, whereas only historical reported counts survive. The final generated validation report itself acknowledges the loss, creating an avoidable contradiction between delivery documents.

The implementation report also retains its unqualified opening assertion that required command outputs are preserved in the archive. The recovery record says original baseline-local records were lost. Distinguish any actually available/reconstructed command evidence from unavailable originals rather than implying blanket preservation. The recovered original specifications do exist, so their availability need not be retracted.

Required correction: update the implementation-report output to state that the missing-browser event/counts are historical transcript/report records, its original log is unavailable, and final acceptance relies on the identified fresh/hosted runs. Qualify the archive-preservation claim to the actual available evidence and link the recovery record. Keep historical failure disclosure; do not erase the failed attempt or relabel reconstruction as original evidence.

### H1 draft repair verified during this preflight

The implementer subsequently added exact replacements for both surviving claims. Read the updated generator independently and confirmed that each replacement target occurs exactly once in the current implementation report. Its first replacement now states that recovered historical specifications and fresh repository/CI verification are preserved, while original unpublished command logs were removed and the recovery record identifies the limits. Its second replacement calls the missing-browser run and old accepted local reruns historical transcript records, says their original files were removed, and explicitly denies presenting them as retained original failure bytes.

This addresses H1 in the proposed generated text. The original finding above is retained as review history. Updated generator syntax also parses successfully; inspected repair-stage SHA-256 is `3f44421ebb2d0dc88570a141ccc098fb4a2b76fba6d969d01ad85ba2db709889`. Actual output verification remains pending because the generator must not run before exact-source acceptance. The parent is separately recording fresh repository commands; those must remain labelled fresh, not recovered original command logs.

## D1/D2/D3 handling and draft consistency

- **D1 immutable tools pin:** current Windows handoff sets the full `ed2bf73e4b3f1c52d372196da7006889afeb46c9` value before fetch, verifies that object exists, and uses it for both wrapper extraction and `ToolsRef`. It no longer executes moving FETCH_HEAD. Proposed final wording keeps the tools pin distinct from the newer accepted implementation revision. Appropriate, provided the stated unchanged collector/wrapper bytes remain backed by the preservation check.
- **D2 Windows policy:** current handoff uses an in-memory ScriptBlock instead of a temporary `.ps1` invocation and states that persistent execution policy is unchanged. Available `b3-ci/policy/source-parity.json` identifies `8b4d62913e8e92728efc2fb33bafc6e9be5421fa` and includes policy status PASS, process policy Restricted, persistent policies unchanged and default no-DB access. This preflight read that summary; it did not independently repeat the parent’s artifact-download/digest verification. The new final report links the newer run, so its exact-63c5 native policy result must also be inspected before that claim is finalized. Parent evidence is not a substitute for the new run.
- **D3 stale finalization wording:** the proposed validation report replaces the old pending/re-run-required narrative, separates accepted executable SHA from the later documentation-only tip, and updates the recovery record’s stale fresh-validation requirement. H1 identified an evidence-availability inconsistency in the implementation report, subsequently addressed by the draft repair above. Delivered-tip acceptance and archive DELIVERY.json are future finalization obligations at this preflight, not yet verified facts.

## Checks and accurate draft boundaries

- Parsed generator syntax successfully without running it.
- Read `FRESH_LOCAL_ACCEPTANCE.json`: reviewed module/test hashes match the earlier independent S1 closure; full1968, focused54, fixture orders41, characterization17, separate Chromium43 and all15 local categories are PASS with no listed failures/errors/skips. Node category is PASS; its 20-case count is supplied elsewhere in the finalization evidence rather than numeric in this JSON. No new test execution was performed here.
- Read preservation summary: status PASS, 849 unchanged main blobs, 14 migration files, with only the existing collector/workflow identified as intentionally changed base files. This preflight did not independently recompute the whole preservation manifest.
- Proposed counts 103 B3 =35 authority +42 attribution +26 collector, plus45 unchanged B1 +four original collector =152, are internally consistent with the scoped change and prior review history.
- The draft candidly retains the earlier failed Windows attempt, its timeouts, lack of full XML, and uncertain resource cause. It does not claim a proven infrastructure diagnosis or hide failure under an allowance.
- Recovered reviews and missing original local evidence are explicitly distinguished from authentic available GitHub artifacts and fresh reproductions in the proposed validation report and recovery record.
- B3-A source-only acceptance remains separate from BLOCKED/NOT STARTED B3-B, BLOCKED installed authority, NOT AUTHORIZED deployment and blocked Gate C progression. No merge, live binding, migration application, provider/task path or production-data access is authorized by the proposed text.
- Final executable acceptance and final documentation-tip acceptance are distinguished. The final output must not imply that the latter has already passed until its own exact-source artifacts are inspected.

No outstanding Important/Critical finding in the repaired proposed handoff text. After successful exact-run artifact inspection and generation, the actual final files remain eligible for a targeted consistency closure; this preflight is not that closure.
