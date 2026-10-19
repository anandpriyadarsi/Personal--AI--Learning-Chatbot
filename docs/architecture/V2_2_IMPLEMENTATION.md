# Architecture V2.2 implementation and private fixture contract

Execution authority: owner-supplied 19 October 2026 V2.2 master prompt.
Base: `c7998c113f9c7e36e00fcf5274bd79a60b486eb1`. No merge, deployment,
production migration, live database access or IKS course import is authorised.

## Implementation plan

- Repair the existing validator environment boundary with explicit
  `--private-fixtures`, two fixed role-specific checksums, bounded safe ZIP reads,
  embedded PDF and manifest verification; preserve the four original tests.
- Reject ambiguous/native-foreign paths, symlinks/junctions, hardlinks, missing
  inputs, swapped roles, different bytes and files within source/artifact roots.
  Keep provider variables excluded and source export independently synthetic.
- Correct A/D at their existing source owners; retain descriptive scores while
  excluding strong observations from recovery and unreviewed historical mapping
  from authority. Do not enable Gate C0 automatic eligibility.
- Reconcile B3 exact evaluation identity against current writer contracts.
- Repair pending result links and boundary errors. Bind scheduled approvals to
  original process-local availability/timezone/policy context, fail closed after
  context loss, and defer durable versioned persistence to owner review.
- Run direct original fixture acceptance, focused regressions, full strict local
  validation, hosted Ubuntu/Windows synthetic validation and independent reviews.
  Publish only redacted synthetic evidence and exact gate distinctions.

## Private source transport and opt-in

No CI runner has access to ChatGPT attachments automatically. The existing
public hosted architecture workflow continues to require zero skips; an absent
private source is BLOCKED and is never replaced by a synthetic ZIP.

The new dispatch-only `architecture-private-fixtures.yml` supports preprovisioned
trusted **Linux and Windows** runners. The owner must provision a restricted
runner group, labels `self-hosted`, `anvaya-private-fixtures`, `Linux`/`Windows`,
and protected environment `anvaya-private-fixture-validation` with an owner
approval rule. The runner service must expose `ANVAYA_PRIVATE_FIXTURE_DIR`, a
private directory outside all checkouts and artifact roots containing the two
unchanged originals named in issue #22. Use ephemeral isolated runners without
other repository access. Install Python **3.12 or later** (required for Windows
junction rejection), the tracked requirements, Git, Node 22 and
fresh Playwright Chromium before provisioning private files. Dispatch only an
owner-reviewed exact SHA. Do not attach these runners to pull-request workflows.

For local trusted execution, set `ANVAYA_TEST_RECOVERED_PILOT_ZIP` and
`ANVAYA_TEST_BAD_V3_ZIP` to canonical absolute local file paths in the same
process and run:

```text
python scripts/architecture_validation.py --require-clean --private-fixtures --output <external-validator-owned-output>
```

Private staging copies the unchanged verified originals into an ephemeral
restricted directory outside source and artifact roots, verifies those bytes
again and marks the files read-only. It never extracts ZIP members or retrieves
content over the network. The opt-in passes only validated staged paths, never
arbitrary variables, credentials or shell commands. The runner owner must ensure
the Windows service account's temporary root has a private ACL; POSIX temporary
directories use owner-only permissions. Unsafe inherited temporary roots fail
before any private bytes are written. Staged files are cleaned on exit.
Logs expose fixed command structure, outcome IDs and checksums. Private-source
JUnit keeps the four original acceptance IDs and anonymises other private-mode
case IDs; assertion/captured payloads and raw stdout are withheld. Raw diagnostics
are confined to a separate private temporary directory and cleaned even on parse
failure. Optional Learning
screenshots are disabled because the unchanged external browser test displays
real slides. Synthetic architecture screenshots use their separate directory.
The private workflow uploads no artifacts. Runner owners must securely dispose
of temporary test data, private files and runner disks after retaining only
reviewed redacted results; never upload the run's `source` or temporary databases.

## Authority remains separate

1. Synthetic development: full tests, browser, Node and integrity gates on the
   exact feature SHA, including cross-platform hosted results.
2. External source acceptance: the four unchanged original checks with verified
   originals and zero skips on each platform. Local Linux alone is insufficient
   for cross-platform acceptance.
3. Installed production authority: BLOCKED pending owner-authorised backup-based
   read procedure and genuine installed Windows B3/WAL evidence. No synthetic
   result grants this authority.

PR #20 (Learning visuals), PR #13 (B3 corrective branch), and PR #9 (C0 pure
simulation) remain separately owned. This branch does not merge or rewrite them.

Rollback is branch-only: close the draft PR or revert its source commits after
review. No records, histories, unrelated branches or installed databases need
deletion or repair.
