# Prior independent B3 review dispositions — transcript recovery

Recovered 2026-10-14 from this reviewer's retained conversation context after workspace maintenance removed the original evidence directory. This is a concise reconstruction, not an original-byte restoration. No new code, document, CI or production review was performed during recovery. The records below originated on 2026-10-13.

## Whole-delta source review, 2026-10-13

Original baseline: `e15c347e5a7bf58c7ec29708eee49b1fed13f712`. Reviewed the then-uncommitted authority DTO/inspector, attribution composition, enhanced collector, tests, source-only spec/plan and primary B3 prompt. Later included the PowerShell wrapper, Windows CI identity step and actual default CLI test. Four Important findings, no Critical finding:

| ID | Reproduced finding | Original evidence |
|---|---|---|
| R1 | Incomplete required-FK adapter could report malformed normalized authority as PASS | Removed `questions.assessment_id` FK in disposable schema, inserted an orphan question: ledger/schema/identity PASS, zero FK violations, integrity true and collector PASS |
| R2 | Nested mutable B1 provenance survived the B3 composition boundary | Replaced `source_refs` with a list, composed, then appended a reference: returned observation changed while stored fingerprint stayed unchanged |
| R3 | Malformed promoted controls passed via legacy coercion | SQLite control with `cutover_id:null` and `promoted_at:null`, valid digest strings and true legacy-write block returned backend sqlite/status PASS |
| R4 | TEMP tables could shadow MAIN authority in the reusable inspector | Corrupted MAIN migration checksum, supplied valid TEMP migration ledger before query-only/BEGIN: inspector reported ledger/schema PASS while MAIN remained wrong |

Initial independent focused execution: **121 passed in 5.78s** using the then-available `../.venv/bin/python` with `PYTHONDONTWRITEBYTECODE=1`. Updated collector suite including actual CLI: **20 passed in 1.22s**. Concrete reproductions were independently executed. `git diff --check` passed; inspected protected B1/B2 source, migrations and full assessment design had no baseline diff. No new substantive issue was found in the initial wrapper/workflow additions, although actual Windows execution remained pending then.

Subsequently, the implementer reported and documented repairs: all 51 required FK edges plus independent orphan counts; deep immutable B1 validation at the B3 boundary; exact raw control typing and aware timestamps; MAIN-qualified queries plus TEMP rejection. During the later document review this reviewer read `review-closure.md` and parsed `review-green.xml`: **145 PASS**, comprising 96 new B3 cases, 45 unchanged B1 and four original collector cases, zero failures/errors/skips. That was verification of the author-run repair evidence, **not a new independent whole-delta repair rerun**. The document explicitly stated this distinction. Parent messages describe R1–R4 as closed at `ed2bf73`; this recovery does not strengthen that historical claim.

## Delivery-document review, 2026-10-13

Reviewed six documents at `ed2bf73e4b3f1c52d372196da7006889afeb46c9`: implementation report, automated validation report, authority contract, minimal Windows handoff, Gate C readiness and next-work prompt. Read primary prompt, author review closure, accepted local summary and preserved assessment specification. Two Important handoff issues and one minor/finalization issue:

| ID | Original disposition |
|---|---|
| D1 — Important | Handoff executed moving branch `FETCH_HEAD` rather than a pinned accepted tools commit; requested immutable tools SHA for both extraction and ToolsRef |
| D2 — Important compatibility limitation | Temporary unsigned `.ps1` invocation assumed a script-permitting Windows policy; Restricted client defaults/AllSigned were not covered by Linux PowerShell or hosted Server policy; requested a tested compatible approach or explicit bounded limitation, with no persistent policy override |
| D3 — Minor/finalization | Validation report retained stale “fresh rerun required” wording despite appended successful rerun, and final exact-source SHA/hosted links remained pending |

D2 was a documented-platform finding, not a local Windows reproduction. Official Microsoft PowerShell 5.1 source consulted on 2026-10-13: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1 . It describes Restricted as the Windows client default and disallows script files while permitting interactive commands.

Local report counts and gate honesty were otherwise accurate: B3-B and installed production authority blocked; production deployment not authorized; no Gate C/live/schema unlock from synthetic success. Scope limits for projection freshness and incomplete full-DDL parity were explicit. The local accepted summary `run-0btr6tiv` showed all 15 categories PASS while hosted aggregate remained pending at that review time. Future policy figures matched the preserved assessment design. The full bootstrap log supported only its disposable tested environment.

The subsequent targeted review inspected the newer Restricted-policy workflow at `8b4d629` and found no additional Important/Critical static problem, while withholding hosted execution acceptance because its then-current run had failed before the step. A separate new S1 scope finding was independently closed on 2026-10-14, recorded in `independent-scope-closure.md` with exact hashes. No separate independent D1–D3 final document-closure review is present in this retained conversation.

## Recovery limits

Historical test totals and hashes above are transcribed from actual earlier tool results in this conversation. Original XML/log/report bytes are not recreated here, and the recovered Markdown must not be represented as an original artifact or newly executed evidence. Current source/CI status requires separate verification. No production permission is inferred from any recovered disposition.
