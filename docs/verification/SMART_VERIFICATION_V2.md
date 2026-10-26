# Smart Verification V2 operator guide

## Authority and levels

Fast feedback reports `FAST FEEDBACK PASS — NOT RELEASE CERTIFICATION`. A fast green is not permission to merge, certify Android or publish an APK.

| Level | Trigger / command | Coverage and limits |
| --- | --- | --- |
| 1: fast | Every open PR update, including draft; manual `stage=fast` | Dependency graph closure, mandatory synthetic academic/security invariants, affected smoke/API tests, changed tests, UI browser smoke, selected Node contracts, source compilation and whitespace. Independent commands execute concurrently. |
| 2: stable feature | Mark PR ready for review; update a ready PR | Existing named feature gates and canonical Linux/Windows architecture validator remain mandatory. This deliberately conservative full superset retains all acceptance contracts while measuring future scope reductions. Local `--stage feature` selects complete affected regressions; broad/unknown/shared changes expand to the entire Python inventory. |
| 2: combined candidate | Push an `integration/**` candidate, or dispatch integration with exact expected SHA | Calls the SAME reusable canonical architecture workflow once. Does not reuse source-branch success. Reports installed Android/private/phone acceptance separately. |
| 3: frozen release | Dispatch `verification-release.yml` on the frozen candidate branch with its full SHA | Canonical full Linux/Windows validation and build-once JVM/installed API31/API35 Android in parallel. Certification blocks without exact-SHA protected private and real-phone evidence. No publishing or main merge occurs. |

Branches should have an open PR for ordinary feedback; there is no duplicate feature `push` trigger in the shared workflow. Full acceptance on `main` still runs after integration. Historical explicitly dispatched workflows retain standalone full testing.

## Selection and fail-safe rules

`scripts/verification_policy.py` owns source ownership, provider-to-consumer edges, required smoke references and complete affected-feature inventories. `smart_verify.make_v2_plan` exposes it without breaking V1 `make_plan` or CLI callers. `verification_coordinator.py` uses this graph for execution; original four-stream labels are retained for report compatibility.

Components include core, learning, library/knowledge, media, assessment, tutor/coding helper, planning/analysis, Android, security, persistence, UI and CI. Examples:

- Core/routes, security and persistence expand to every affected consumer.
- Library documents/search include library, learning and tutor. Native providers include media, library, UI and their consumers.
- Assessment presentation expands to secrecy, persistence and UI safety, including broad public regressions at feature level.
- Unknown files expand to all components. Missing merge-base creates a broad BLOCKED report; canonical full acceptance is required rather than guessing changed files.
- Missing/deleted changed tests or required inventories block execution. Renames include both old and new paths. Selected tests with skips are not marked passed by the scoped runner.

This is an explicit maintained graph, not a proof of complete semantic dependency discovery. Add edges when introducing new shared modules. Filename ownership alone never certifies release.

```bash
python -m pytest -q tests/test_smart_verify.py tests/test_verification_coordinator.py tests/test_verification_v2.py tests/test_verification_benchmark.py
ANVAYA_BROWSER_TESTS=1 python scripts/verification_coordinator.py --base BASE_SHA --head HEAD --execute
ANVAYA_BROWSER_TESTS=1 python scripts/verification_coordinator.py --base BASE_SHA --stage feature --execute
```

Linux commands are shown; on PowerShell set `$env:ANVAYA_BROWSER_TESTS='1'` before invoking Python. Install the tracked requirements and Chromium first. Full scoped execution containing the four original private tests may block on their missing fixtures; use the canonical validator's audited public/private split. Never change their skip rules to obtain green output.

## Evidence and trust

Reports contain exact source/tree SHAs; workflow/script, selected-test and environment fingerprints; OS, Python/packages, Node, Java compiler/Gradle/SDK availability; test results, omissions, duration, commands, log references and limitations. GitHub artifacts add workflow run/attempt identity. The canonical validator retains its independent source manifest, full JUnit inventory and named private-fixture omissions.

Local JSON is diagnostic only. `verification_evidence.reusable` rejects changed trees, test implementations, stages, dependencies, configurations, dirty tracked source, stale/expired artifacts and failed/skipped jobs. It additionally requires authenticated trusted workflow provenance and independently verified immutable artifact digest/ID. **Automatic cross-run remote reuse is deliberately disabled** until that provenance verifier is provisioned. No user-editable JSON bypass exists. The practical reuse enabled here is one canonical implementation and build-once APK sharing within a single Actions run, with exact source and SHA256 checks.

`verification_release.py` reads run/job metadata from authenticated GitHub APIs, requires exact SHA and workflow/job identities, and rejects missing, skipped, cancelled or foreign-repository gates. The phone workflow is intentionally not fabricated. A real protected phone procedure must be implemented/reviewed before its gate can pass. Private workflows must be dispatched from the frozen branch with the same reviewed SHA; a default-branch run testing an unrelated checkout is insufficient.

## Four-stream integration

`verification/streams.json` stores branch names, related PRs, declared dependencies and nine required cross-feature scenarios, never permanent source SHAs. The live resolver queries GitHub branch heads, PR bases, comparisons and exact-head workflow metadata every run. API errors and truncated inventories remain visible blockers. The checked-in dated snapshot is a historical observation, not current certification.

```bash
GH_TOKEN=READ_ONLY_TOKEN python scripts/verification_integration.py --preview --output integration-manifest.json
```

The workflow supplies a read-only token automatically; do not put literal token values into scripts or documents. For local use, configure the token through your normal secure environment. Fetch full remote histories first. Preview uses `git merge-tree` and `git commit-tree`, writes local Git objects only, and does not checkout, push, update refs, change a developer branch or merge main. Ancestors already included by a descendant are omitted; independent overlapping changes are reported. Conflicts block a candidate. A prepared candidate is `PREPARED_NOT_VERIFIED` until that exact candidate tree passes every required integration scenario.

To add a stream, add a new uniquely named entry with its source branch/PRs, then extend graph ownership and regression scenarios. Declared dependencies are descriptive; Git ancestry determines safe stacking. A human must reconcile semantic dependencies and any conflict before creating a real integration branch. The current dated preview reports a conflict; no complete integration is claimed.

## Workflows, caching and cancellation

- `smart-verification.yml`: one PR feedback entrypoint, concurrent commands, explainable plan/evidence artifact; only ordinary feedback cancels superseded runs.
- `architecture-validation.yml`: stable required names and full validator retained; reusable by integration/release; only `main` push avoids duplicate legacy branch push+PR runs.
- `verification-android.yml`: reusable native source checks; integration builds APKs once and passes the exact same app/test APK bytes to API31/API35 emulator jobs. No application uninstall/reset shortcut.
- `verification-release.yml`: frozen candidates are not cancelled by development updates. Missing Android source or tooling fails; source-only tests cannot replace installed tests.
- `verification-integration-manifest.yml`: read-only live resolution/preview; conflicts are failures, not green integration.
- `verification-benchmark.yml`: existing real-run timing audit plus identical-source, identical-scope serial/parallel scheduling comparison. Runner consumption sums actual job runtimes, separate from wall time and queue.

Python keys hash all root requirement files, including recursively referenced dependency files. Chromium caches are OS/Python/dependency-content addressed. PRs restore browser caches only; only default-branch pushes save them. Gradle is read-only outside trusted default-branch runs. Do not cache test stores, private fixtures, student documents or credentials. Generated synthetic APKs are same-run artifacts, never dependency caches. No signing keys or production user data are uploaded.

## Failure diagnosis and retries

Artifacts include the exact failed command, duration, log path, reproduction command and investigation category. Categories include assertion/source regression, dependency, browser, Android, infrastructure, integration conflict, private fixture, missing verification and indeterminate. Retry success alone never marks a test flaky; there is no automatic retry hiding failures.

Use Actions → failed run → **Re-run failed jobs**, or the GitHub connector's rerun-failed-jobs operation. Preserve earlier attempts. Rerun only after investigating the first error and confirming whether source/environment changed. A new source SHA needs new evidence.

## Protection and remaining release requirements

Live audit on 25 October 2026 found `main.protected=false` and no rulesets. `verification/main-ruleset-proposal.json` is a proposal only; an owner with administration permission must review/apply it. It requires fast feedback, canonical cross-platform and Assessment acceptance, with review and no force pushes/deletion. Confirm actual check names before activation and add the installed/private/phone contracts for release branches once provisioned. Draft/N/A job results never constitute acceptance evidence; only a ready candidate with executed mandatory jobs is merge-eligible.

The Android workflows are implemented but cannot be executed on this main-based branch because Android application sources are still on unmerged feature branches. Installed lifecycle, external-player grants, original documents, update/backup/restore, private originals and physical-phone acceptance remain required on the reconciled unified tree. No emulator, real-phone, signing or APK certificate is implied by desktop/browser tests.
