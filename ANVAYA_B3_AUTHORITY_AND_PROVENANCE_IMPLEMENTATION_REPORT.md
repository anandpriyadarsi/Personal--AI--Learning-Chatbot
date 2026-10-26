# B3-A source-only implementation

Accepted executable/test/workflow revision: `63c5a636f4e737c204a791360e2bc715c9ac945f`; [Ubuntu/Windows/aggregate acceptance](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38525732263). Documentation-only delivery metadata is in the final archive and exact-source Actions artifacts.

Starting main: `e15c347e5a7bf58c7ec29708eee49b1fed13f712`, PR8 merged B1/B2. Dedicated branch: `anvaya/topic-intelligence-b3-attribution-authority`, merge base the same main SHA. GitHub main/branches/latest PRs and all three PR integration jobs were verified before edits; no pre-existing B3 branch. Recovered historical specifications and fresh repository/CI verification are preserved in the evidence archive. Original unpublished command logs were removed by workspace maintenance; the recovery record identifies their limits. Historical backup.py/dashboard.py CRLF-only differences were handled by the existing checked checkout-EOL helper; no substantive main work was reset or overwritten.

## Implemented paths

| Path | Concrete behavior |
|---|---|
| domain/b3_authority.py | Frozen typed aggregate authority/projection records and explicit status enum |
| repositories/sqlite/b3_authority_repository.py | Deterministic query-only manifest, source ledger, required schema/all51 FK relationships, orphan/course/bridge checks, nine projection statuses, exact course/topic ID parity and honest freshness |
| domain/b3_attribution.py | Strict immutable attribution DTOs and deterministic composition of unchanged B1 observations; historical unknowns and explicitly pinned reviewed synthetic fixtures |
| scripts/architecture_local_collector.py | Enhanced existing collector, no DB default, strict redacted backend checks, complete main/WAL/SHM copy verification, private query-only inspection/disposal and aggregate B3 report |
| scripts/b3_collect_authority.ps1 | Runs tools from a source-only archive outside the installed tree, using the existing interpreter; optional explicit closed-writer attestation |
| .github/workflows/architecture-validation.yml | Unchanged full Ubuntu/Windows validator plus actual Windows PowerShell identity collection and redacted output artifact |
| tests/test_b3_authority.py, test_b3_attribution.py, test_b3_collector.py |103 new cases including adversarial review regressions and actual default CLI |

Domain and repository paths above are relative to personal_learning_assistant; other paths start at the repository root. The B3 authority/attribution adapters are disconnected from production routes/services. B1 remains the explicitly attested closed sidecar-free immutable reader; B2's live WAL-aware query-only boundary is unchanged. Neither is promoted into a new live B3 path.

One evaluation remains one observation; bridge IDs/content equivalence stay separate. Mapping review/calibration, grading, authoring and self-confidence stay separate. New composition never regrades, computes mastery/recovery, mutates a mapping, creates a task or infers exam independence. Exact current mapping/package fields do not acquire historical trust. The output retains exact top-level TopicIdentity, stored manual status and student self-confidence even when evidence is empty; fingerprint scope includes that identity without turning it into performance evidence. Unflagged course/topic mismatches are rejected; original B1 cross_course_source records remain visible and are never rebound.

## Safety and limitations

No production database/control/vault was accessed or copied during development. All SQL test data are disposable. No applied migration changed or new migration number allocated. Full Assessment pause/offline subjective design and current Assessment/Coding Helper functionality remain unchanged. No deployment or main merge.

The inspector's PASS schema scope is its required columns/FK adapter, not every DDL/index/trigger. Course/topic projection identity is implemented; other projection parity and all positive freshness guarantees remain UNVERIFIABLE. Current schema has no historical immutable review/independence snapshots. Collector's schema PASS means stable copied schema checks only; production authority always remains BLOCKED. Process enumeration cannot prove absence of hidden writers.

## Review and validation

Base local full1865/Chromium43/Node20/all15 categories PASS. B3 fail-first runs: authority23 FAIL before module; attribution30 FAIL before module; collector16 FAIL/two already passing; invalid-control copy and actual CLI missing-field regressions FAIL before implementation. Four independent Important findings were reproduced and fixed: incomplete FK verification, mutable nested B1 provenance, promoted-control null coercion and TEMP table shadowing. Supplemental scope fix focused152 PASS includes103 B3 +45 unchanged B1 +four unchanged original collector cases. Supplemental independent S1 scope mismatch finding was also reproduced and closed;87 attribution/B1 cases and five independent adversarial checks passed. No Critical finding; closure is supported by RED/GREEN records and the full validation report.

PowerShell7.4.13 tools-only default command executed successfully on a disposable source snapshot; exact Windows PowerShell acceptance is provided by hosted CI. The initial missing-browser43 setup-error run and subsequent accepted local reruns are historical transcript records; their original unpublished files were removed by maintenance. Fresh restored full validation and authentic recovered hosted artifacts provide final acceptance. This history is not presented as original retained failure bytes.

Accepted executable SHA, hosted run links, source fingerprints and documentation-only delivery acceptance are recorded in ANVAYA_B3_AUTOMATED_VALIDATION_REPORT.md and the GitHub Actions exact-source artifacts. Recover the implementation from this branch, not a premerge B2 patch. B3-B and Gate C are not unlocked by B3-A success.
