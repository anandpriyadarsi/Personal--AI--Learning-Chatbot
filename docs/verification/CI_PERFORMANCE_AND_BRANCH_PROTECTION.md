# Smart Verification V1.1 — Real timing and merge-safety follow-up

Date: 23 October 2026. Evidence is from public **synthetic GitHub Actions CI only**.
No local academic records or API secrets were read.

## Observed performance, not an invented speedup

The earlier user-reported ~45 minutes of verification is not a controlled timing
baseline. The following are independently fetched **successful** GitHub Actions
jobs from two different PRs and commits. Wall clock is measured from the first
relevant job's \`started_at\` to the last relevant job's \`completed_at\`;
it excludes GitHub's queue delay. Changing source code and runner conditions
mean these are **observations, not causal before/after experiments**.

| Gate | Earlier run | Smart V1.0 run | Observed difference |
| --- | --- | --- | --- |
| UI V2 Ubuntu + Windows jobs | [#39797255775](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39797255775), 26m31s | [#39886333220](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39886333220), 11m28s | 15m03s faster (~56.8%) |
| Canonical full architecture, both OSes + acceptance job | [#39883294409](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39883294409), 28m50s | [#39886333214](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39886333214), 32m02s | 3m12s **slower** (~11.1%) |
| Smart V1.0 early feedback | Not implemented | [#39886333238](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39886333238), 29s | New early signal, **not** merge authority |

The earlier UI V2 workflow ran a full regression on both OSes. The Smart V1.0
workflow skipped those *duplicate* PR full-regression steps, while keeping the
focused UI browser gates, and the canonical full regression on Ubuntu and
Windows. This explains why UI V2 could become faster, but does not prove a
15-minute reduction in total PR time: the canonical Windows full validator
remains the critical path.

Example full validator timings from the same two successful architecture runs:

- Earlier Ubuntu: 15m03s; Smart V1.0 Ubuntu: 12m43s.
- Earlier Windows: 26m36s; Smart V1.0 Windows: 30m18s.

**Conclusion:** Smart V1.0 improves feedback latency and removes duplicate
work but a 5–10 minute *total merge gate* is **not achieved or claimed**.

## Automated reproducible benchmarks

The script \`scripts/verification_benchmark.py\` accepts read-only JSON from
GitHub Actions \`GET .../actions/runs/{id}/jobs?per_page=100\`. It fails closed
for incomplete jobs, missing platforms, absent timing/required test steps,
failed runs, and duplicate names, and emits JSON plus Markdown.

~~~sh
# Requires the 'gh' CLI authenticated with Actions read access.
REPO=anandpriyadarsi/Personal--AI--Learning-Chatbot
gh api "repos/$REPO/actions/runs/39883294409/jobs?per_page=100" > before.json
gh api "repos/$REPO/actions/runs/39886333214/jobs?per_page=100" > after.json
python scripts/verification_benchmark.py --before before.json --after after.json \
  --group architecture \
  --before-run "https://github.com/$REPO/actions/runs/39883294409" \
  --after-run "https://github.com/$REPO/actions/runs/39886333214"
~~~

Use \`--group ui\` with runs 39797255775 and 39886333220 to reproduce
UI measurement. \`--group fast\` compares runs containing the same fast-job name.

The \`.github/workflows/verification-benchmark.yml\` workflow runs offline
unit tests on benchmark changes. **After this workflow is merged into main**,
each successfully completed canonical architecture-validation workflow
automatically triggers a read-only timing report, comparing the current full
gate against the successful pre-V1.0 reference #39883294409. This is
non-blocking observational reporting, not a merge safety bypass. It never
executes source from an untrusted PR or calls an AI provider.

## Critical: branch protection is STILL NOT ENABLED

On October 23, 2026, GitHub's branch endpoint returned
\`main.protected=false\`, and the repository rulesets list was empty.
The connected GitHub App does **not** expose branch protection/ruleset
mutation methods, and the legacy protection read was denied (403).
**No action in this PR enables branch protection.** Adding YAML alone
cannot prevent a direct push or an administrator's unchecked merge.

### Repository owner one-time UI configuration

Open the repository on GitHub with an admin account:

1. **Settings → Rules → Rulesets → New branch ruleset** (or the available
   Branch protection rules settings UI).
2. Set branch target to **main** and set ruleset enforcement to **Active**.
3. Select **Require a pull request before merging**. For a one-person
   repository, do not enable mandatory external review approvals unless
   reviewers are actually available.
4. Select **Require status checks to pass** and add exactly these GitHub
   Actions job names:
   - \`Cross-platform development acceptance\`
   - \`Change-aware Python and JavaScript smoke\`
5. Restrict force pushes and branch deletion, and remove blanket admin-bypass
   exemptions if you want the rule to apply to your own merges.
6. Save the rule. Check on GitHub that \`main\` is protected, that both
   required checks are recognized on a test PR, and that a failing test or
   pending check blocks merging.

If using a ruleset instead of legacy branch protection, API checks should
inspect the **active ruleset targeting main**; a \`protected\` flag alone
does not prove the named required statuses are enforced. A repository admin
must verify the exact rule and that no bypass grants invalidate it.

Do **not** merge a failing or pending check merely to test the rule. Open a
disposable draft PR and inspect the merge box or deliberately create a failing
CI test in a disposable branch, then close it without merging. All academic
data and Tutor/Android branches remain untouched.

## Limits

- Existing four unavailable external IKS tests are blocked certification, not
  passes. Real-provider Tutor acceptance and real-device Android testing still
  require their own evidence.
- Faster fast feedback does not mean faster required full regression.
- Runner setup, CI concurrency and GitHub queues are external factors.
- Changes in tests or application code between observations prevent strict
  apples-to-apples causal attribution; collect multiple comparable runs.

## V1.1 final repair, 23 October 2026

The original Ubuntu failure in run [39901787974](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39901787974)
was `test_student_manually_chooses_study_then_rechecks_exact_revision[1366]`.
`academic_inventory()` recursively hashed every file before filtering to the
canonical academic database. An asynchronous Learning Studio bookmark transaction
removed `learning_studio.sqlite3-journal` between enumeration and reading, causing
`FileNotFoundError`. This is a test-instrumentation race, not evidence of a broken
academic assertion. The original artifact's traceback, manifest hash, archive
hashes and category results are preserved in `evidence/v1_1/original-failure.json`.

Current main already contained the targeted fix and two regression tests after
Tutor #32 landed. PR #37 incorporates that accepted main commit, retaining the
same canonical database/WAL/SHM mutation assertions. It does not reimplement the
Tutor fix or change the Tutor/Android branches.

Selector repair now retains both sides of a rename, requires full coverage for
deleted tests or missing mapped tests, and fails closed for all unrecognized
paths (including native Android and configuration files). Fast feedback still
never grants full merge authority. Benchmark repair rejects skipped full/smoke
steps and inconsistent run/source identities. Matching run metadata enables
queue time and elapsed-from-creation measurements; individual step durations
separate dependency, browser and artifact costs. Without metadata, queue time is
explicitly unavailable. The canonical validator now prints the slowest 25 setup,
call and teardown phases in each pytest log. Artifacts use the source head SHA,
rather than the PR's synthetic merge-ref SHA, and checkout verifies that head.

### Measured bottleneck and decisions

Original PR #37 run, source `a27c82f7766930ed4d95e14adb4ff49c11eb586f`:

| Stage | Ubuntu | Windows |
| --- | ---: | ---: |
| Dependency installation | 23s | 58s |
| Fresh browser installation, including OS libraries on Linux | 22s | 13s |
| Python full suite (JUnit suite elapsed) | 647.170s, FAIL | 1781.607s, PASS |
| Focused feature verification | 5.776s | 17.250s |
| Forward fixture-order check | 4.223s | 9.469s |
| Reverse fixture-order check | 7.078s | 25.453s |
| Characterization | 9.434s | 31.297s |
| Additional protected headless browser gate | 66.672s | 110.406s |
| Artifact upload step | 3s | 3s |
| Full validator step | 12m26s, FAIL | 33m09s, PASS |

Workers began together at 04:43:17Z; aggregate ended at 05:18:15Z:
**34m58s** active critical path, excluding initial queue, with Windows dominant.
This failed workflow is diagnostic evidence, not a successful performance sample.
JUnit includes fixture overhead in testcase time; the new `--durations=25`
log separates setup/call/teardown for future diagnosis.

Windows full-suite time by test module in this diagnostic run: read-safety
166.139s, Assessment browser 94.709s, Planning/Analysis browser 64.093s,
question-topic dual-read 53.366s. These involve source exports, fresh SQLite
state, subprocesses and browser startup. No single fixture accounts for the
entire critical path. Removing their assertions or sharing mutable databases
would not be an acceptable speed optimization.

Two historical successful architecture samples span **28m50s–32m02s**, median
**30m26s** (n=2, different commits and runner conditions). Their initial queue
was 19s and 3s; elapsed from workflow creation was 29m09s and 32m05s.
This is a small observational sample, not controlled causal evidence.
The historical UI jobs span 26m31s to 11m28s, but the full Windows critical
path prevents treating that reduction as an equal total-PR improvement.

Decisions: retain existing reproducible pip caching; do not cache academic
SQLite files; reject blanket xdist/sharding and shared browser/database fixture
changes because independence is not established. Repeated source setup is a
candidate for later work only after the per-phase diagnostics establish its
benefit. No additional full-suite runtime reduction is claimed by this repair.
Avoid a costly speculative optimization merely to produce a speedup number.

### Administrator blocker and exact enforcement settings

Refreshed GitHub reads: `main.protected=false`, rulesets `[]`; legacy protection
GET returns **403 Resource not accessible by integration**. No protection write
operation is exposed by the connected GitHub tools. Enforcement and bypass
configuration therefore remain **BLOCKED**, not enabled by this PR.

Owner must create an **Active** branch ruleset targeting **main** (not all feature
branches), require a pull request and these exact required checks from **GitHub
Actions**:

- `Cross-platform development acceptance`
- `Change-aware Python and JavaScript smoke`

Enable **Require branches to be up to date before merging**. Keep applicable
independent feature checks; do not substitute smoke for either platform's full
regression. Restrict deletions and block force pushes. Leave the ruleset bypass
list empty; do not add repository-admin or all-app blanket bypass. A one-person
repository need not require an external approval reviewer. Save as **Active**.

Verify the effective target, required check names, source app and bypass list
in Settings, then inspect a disposable non-draft test PR: failing, missing and
pending required results must each keep merging blocked, and both native OS
jobs must be successful at its exact head before the aggregate passes. Close
the disposable PR without merging; do not merge intentionally failing code.
The actual enforcement probe cannot be performed until the administrator enables
the rule. PR #37 remains unmerged pending user approval and this external blocker.
