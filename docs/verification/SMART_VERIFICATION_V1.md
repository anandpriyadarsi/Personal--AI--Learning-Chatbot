# ANVAYA Smart Verification V1.0

Status: **draft; do not merge until native CI evidence is reviewed**.

## Problem and measured baseline

ANVAYA's Mobile V1.0 validation recorded 2,942 passing Python cases in
611 seconds for **one** Python full-suite invocation. Before this change,
the Architecture V2.4, UI V2, and Library V2 feature workflows could each
rerun the same full suite on Ubuntu and Windows, while
architecture-validation.yml repeated it again. End-to-end wall time also
includes environment creation, browser fixtures, CI queues, and additional
browser/Node checks; 611 seconds is not a measured 45-minute workflow total.

## Three verification levels

1. **Fast feedback** — CI runs selector invariants, touched-test modules,
   representative area-specific smoke tests and Node contracts. Test scope,
   head commit, duration and any mandatory full follow-up are in
   smart-verification.json and JUnit XML. This is NOT merge approval.
2. **Focused feature acceptance** — all mapped tests (including browser
   modules where selected) can be invoked with --mode focused, while
   existing feature workflows continue running their mandatory focused
   cross-platform browser and correctness gates. An unknown, unsafe,
   shared, or critical changed path refuses focused-only execution.
3. **Full acceptance** — architecture-validation.yml remains the canonical
   PR whole-repository, both-platform source authority. It also runs
   targeted browser/order/fixture verification and preserves the four
   named unavailable private IKS test identities. The four skips are
   BLOCKED external certification, not PASS. Existing manual workflow
   dispatch retains standalone feature full-suite regression.

**Before merging** inspect the architecture-validation result for the
*same* PR head SHA and both platforms; no bypass is permitted. Also
require any separate browser, academic, external-fixture, real-provider,
Android or installed Windows acceptance applicable to the PR. A green
fast-feedback job alone is never sufficient.

## How to run

Requires the project's test dependencies (at minimum the pinned
requirements-learning-studio.txt set).

~~~sh
# At repository root. Pass the PR merge base and a real head commit.
python scripts/smart_verify.py --base origin/main --head HEAD --mode fast --execute

# Expanded test selection: fails closed for shared, ambiguous or unknown changes
python scripts/smart_verify.py --base origin/main --head HEAD --mode focused --execute

# Explicit whole-suite convenience command; canonical certification is still
# scripts/architecture_validation.py and GitHub's two-OS architecture gate.
python scripts/smart_verify.py --changed-file scripts/smart_verify.py --mode full --execute

# Explain or preview selection, no testing:
python scripts/smart_verify.py --changed-file personal_learning_assistant/tutor/policy.py --mode fast
~~~

Do not use --changed-file as an acceptance authority; it is an explicit
developer convenience and can omit files. CI computes the authoritative
changed-file list from Git's merge-base diff with full history available.
A missing base, empty change list or unknown path does not silently imply
safe focused coverage. Changing migrations, requirements, test fixtures,
shared SQLite connection code, or workflows always requests the full gate.

## Workflow deduplication

- architecture-validation.yml remains the sole *routine full regression*
  for PRs (both OSes), and cancels superseded head runs.
- architecture-v24-intelligence.yml keeps its focused cross-OS versioned
  evidence check on PRs; the redundant full step runs on manual dispatch.
- ui-v2.yml and library-resources-v2.yml preserve their required
  browser/feature checks on PRs; their separate whole-suite invocation
  remains available outside the PR trigger (branch push/dispatch).
- smart-verification.yml adds early fast feedback without caching academic
  records, uploading secrets, or claiming that simulated responses are
  real AI provider acceptance.

All modifications are limited to the Smart Verification branch. The
parallel Tutor and Mobile branches are not modified.

## Known limitations / follow-up criteria

- Fast area mapping is deliberately explicit, not dependency-graph proof.
  The cross-platform full regression is mandatory for all PRs.
- Large modules may remain expensive in fast mode; use actual JUnit
  timings before shrinking or sharding any module.
- We have not claimed a 5-minute end-to-end improvement until the exact
  PR head has real CI measurements with green acceptance.
- Browser driver installation and CI worker queues may remain significant;
  optimizing or caching those is a separate measured follow-up.
- Parallel pytest-xdist is **not** enabled: shared SQLite fixtures, ports,
  and live browser state must be audited before sharding.
- Changes to workflow requirements/branch protection must not allow PRs
  to merge without their previously mandatory validation status.
