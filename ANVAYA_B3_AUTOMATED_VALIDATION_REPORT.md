# B3 automated validation and acceptance

Starting main: `e15c347e5a7bf58c7ec29708eee49b1fed13f712`. Feature: `anvaya/topic-intelligence-b3-attribution-authority`. Accepted executable/test/workflow revision: `63c5a636f4e737c204a791360e2bc715c9ac945f`. [Exact-source Ubuntu, Windows and aggregate run](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38525732263) — PASS. This tracked handoff is a documentation/evidence-only descendant; the delivered tip's own source SHA and acceptance are emitted by its GitHub Actions artifacts and recorded in the final archive DELIVERY.json. No source-result substitution across commits.

| Check | Ubuntu | Windows |
|---|---:|---:|
| Full Python, no deselections | 1968 PASS | 1968 PASS |
| Focused existing harness | 54 PASS | 54 PASS |
| Fixture order: agent first | 41 PASS | 41 PASS |
| Fixture order: phase2 first | 41 PASS | 41 PASS |
| Characterization | 17 PASS | 17 PASS |
| Separate real Chromium | 43 PASS | 43 PASS |
| Node | 20 PASS | 20 PASS |
| All validator categories | 15 PASS | 15 PASS |
| Failures / errors / skips | 0 / 0 / 0 | 0 / 0 / 0 |

There are103 new B3 cases (35 authority,42 attribution,26 collector), added to the unchanged1865 baseline. The separate B3+B1+original collector focused run has152 PASS. Selected fail-first diagnostic runs use narrow case selection; the full acceptance suite has no skips/deselections/baseline allowances or weakened assertions. Real Chromium and synthetic providers exercise the existing UI; no new B3 UI/live binding is claimed.

Clean hosted source manifests identify `63c5a636f4e737c204a791360e2bc715c9ac945f` with dirty=false. Physical source fingerprints: Ubuntu `0986561edf3ffeec37da8912ac7c68924a47c68aaf725cec8c46458ec212701e`, Windows `100cafa45f20d67d28e3af89f42bc8f6897819a45d90a5e2890711a4284e2bac`. Every manifest file is checked against its Git blob. Any physical difference must be exactly LF/CRLF conversion permitted by existing Git attributes; no substantive executable difference is accepted. Both OS full JUnit case inventories are identical. Native Windows PowerShell also passes the process Restricted-policy collector invocation, confirms persistent policy inventories unchanged and returns the no-DB redacted default. Ubuntu does not stand in for this native test.

Fresh restored local run `run-kslg8z5c`: full1968, Chromium43, Node20, all15 PASS, zero failures/errors/skips; source fingerprint `7b4e107b51151b5775a1bd29912213509ca715b315b77983dee7c9506dac7a1b`. Pre-publication source is recorded dirty=true because reviewed changes were staged; all non-Markdown bytes were compared before publishing. Clean exact hosted acceptance is independent. Python3.12, tracked requirements and finite1800s full/900s other budgets are retained; CI uses Node22 and45-minute jobs. Local Node24.19 is recorded separately, never relabelled as hosted Node22.

## Earlier attempts and availability

- Base local1865/Chromium43/Node20/all15 PASS was recorded before implementation. Merged PR8 [integration38367859776](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38367859776) was verified successful before edits.
- Initial implementation `ed2bf73e4b3f1c52d372196da7006889afeb46c9`: [38405863027](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38405863027), Ubuntu+Windows+aggregate PASS, full1961/Chromium43/Node20, all15. Original downloaded artifacts/logs/XML remain in the archive.
- `8b4d62913e8e92728efc2fb33bafc6e9be5421fa`: [38407985532](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38407985532), attempt1 Windows FAIL: full-suite1800s timeout with no completed XML, characterization17 cases with13 setup errors from read_routes120s timeout and zero assertion failures. Restricted step was not reached. Exact IDs are retained in [FAILED_ATTEMPT.json](docs/verification/b3/FAILED_ATTEMPT.json). Unchanged-source attempt2 passed Windows+aggregate using the already successful Ubuntu job: full1961/Chromium43/Node20/all15 and actual Restricted-policy PASS. Underlying resource cause is unproved; no timeout increase or assertion change was used.
- First local implementation run had43 browser setup errors because its ephemeral executable was missing, followed by recorded accepted1961 reruns. The interrupted local scope run had full1968 PASS but a separate browser failure before scratch pruning; its final case ID/root cause is unavailable. It is not acceptance. Fresh restored full validation above and exact hosted acceptance replace it.

Workspace maintenance removed unpublished original local RED/GREEN, bootstrap and interrupted-browser trace files. Recovered independent review documents explicitly identify transcript recovery. This archive includes available authentic GitHub artifacts and fresh reproductions, without fabricating missing files. [Recovery record](docs/verification/b3/WORKSPACE_RECOVERY.md) states the limits.

## Independent review and preservation

Four original Important findings were reproduced/repaired: missing FK ownership verification (all51 edges plus orphan counts), mutable nested B1 provenance, promoted-control null coercion, and TEMP ledger shadowing (MAIN-qualified queries and TEMP rejection). Supplemental Important S1 topic/observation scope mismatch was independently closed after87 attribution+B1 PASS and five further adversarial checks. Its code/test hashes match the delivered implementation. Two handoff findings were repaired: immutable tools pin and Restricted-policy-compatible in-memory command; final report wording is reconciled to accepted evidence. Recovered original dispositions and supplemental closure are [tracked here](docs/verification/b3/).

All14 existing migration SQL files are immutable;849 unchanged main blobs are verified. Existing B1/B2 reader/router contracts, Assessment/Coding Helper behavior and the full pause/paper specification remain unchanged. No production DB/control/vault was accessed, copied or uploaded. Synthetic fixtures test SQL/query-only enforcement, main/WAL stability and legitimate private SHM coordination. GET/provider/migration/task behavior is not newly bound by B3. A/B/D/P desired-product defects remain FAIL; B2's C desired read-safety behavior remains PASS.

B3-A DEV SOURCE-ONLY: PASS. B3-B WRITER/SCHEMA: BLOCKED / NOT STARTED. LOCAL WINDOWS PRODUCTION AUTHORITY: BLOCKED. PRODUCTION DEPLOYMENT: NOT AUTHORIZED. Gate C remains blocked for product progression. Source-only future merge review is appropriate; merge, release, live paths and production migrations were not performed or authorized.
