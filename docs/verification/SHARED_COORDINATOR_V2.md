# ANVAYA Smart Verification V2 — four-stream coordinator

Smart Verification V2 extends V1.0, but **never declares a changed-file smoke test to be merge/release approval**.

## Four concurrent streams

| Stream | Examples | Additional certification |
| --- | --- | --- |
| Performance + reader + rename | learning reader, Android navigation, display titles | mobile browser, persistence, performance, Android lifecycle |
| Handwritten media | attachment upload, metadata, Android external-player intents | storage integrity, FileProvider permission isolation, installed receiver |
| Native documents | original PDF/PPT(X), inside-file indexing and search | original-byte hashes, large-document limits, Android PDF/view intents |
| Assessment review | red/green answer feedback, grading, independent questions | answer-key secrecy, CBT/handwritten isolation, resumed tests |

**Changing shared bridges, tests, workflow definitions, dependencies or unfamiliar components never authorizes a scoped release.** The coordinator unions affected streams and records uncertainty.

## Everyday development (fast stage)

1. Each Work session retains its own development branch and **draft PR**. Push meaningful changes, not every save.
2. The V2 workflow runs selector invariants and a small cross-stream Python/Node smoke set for the exact PR head, with a JSON artifact and summary. A report saying `FAST_PASS_ONLY` means full acceptance remains pending.
3. Obsolete V2 runs for the same PR/branch are cancelled by the concurrency group.
4. The broad Architecture, Assessment, Tutor, Library, UI and Intelligence workflows do not execute their expensive validation jobs for draft PRs. Their `ready_for_review` event and non-PR dispatch/push paths still run the respective full jobs.

**Make the PR ready for review only when the branch is a stable candidate.** The existing independent acceptance workflows then execute; do not mark it ready before meaningful tests and design review. On subsequent review-ready updates, full jobs rerun at the new SHA.

Note: the repository's main branch currently lacks protection. The owner should enable a ruleset requiring successful canonical CI plus review, disallowing direct pushes and stale approvals as appropriate. A skipped draft job is not an acceptance artifact and must never be used to justify merging.

## Shared integration candidate

Create `integration/<name>` from an approved `main` baseline. Carefully merge/cherry-pick only intended changes, including the existing stacked Android PR ancestry (PRs #42, #44, #47, #49, #51 and #52 must not be naïvely merged multiple times).

Pushing this branch runs V2's **Linux + Windows canonical architecture validator** once as the integrated synthetic gate. Its result is scoped to the integrated commit SHA. Alternately use **Actions → ANVAYA Smart Verification V2 shared coordinator → Run workflow → stage=integration** and provide the exact SHA of the selected branch's HEAD. A mismatch fails closed.

The integration artifact explicitly records:

- Exact source SHA and platform result.
- Android build/emulator/installed lifecycle: **PENDING** unless separately verified.
- Private-fixture/source authority: **PENDING** unless run on protected owner-approved validation infrastructure.
- Release approval: **false**.

If any stream changes after this point, the integrated candidate's source SHA changes; rerun the required integration/Android acceptance. A source branch's green tests are not automatically valid for the merged integration tree.

## Release and Android acceptance

The Android APK and real device path are separate from desktop synthetic CI. Before merging/releasing: run feature-preservation regressions, Android JVM/Gradle build, API31/API35 emulator and installed update/force-stop tests, private-data retention checks, original-document storage and media FileProvider grant checks, then owner phone checks. Preserve signing identity and data; never uninstall an existing data-bearing application as a shortcut.

No pull request may bypass the independent grading, academic-data identity, private fixture, CSRF, authorization, or source-integrity requirements. Avoid removing required checks solely for faster CI.

## Evidence and performance measurement

Compare GitHub Actions `created_at`/`updated_at` and actual job start/end metadata before and after V2 at the same workload and PR state, separating draft feedback latency from ready/integration acceptance. The historical benchmark workflow can be used for reproducible timings; do not claim a speedup without comparable measured runs.

## Useful local commands

```bash
python -m pytest -q tests/test_smart_verify.py tests/test_verification_coordinator.py
python scripts/verification_coordinator.py --base "$(git merge-base origin/main HEAD)" --head HEAD --execute --json shared-verification.json
```

`shared-verification.json` is a **fast-scope report**, not permission to merge or publish an APK.
