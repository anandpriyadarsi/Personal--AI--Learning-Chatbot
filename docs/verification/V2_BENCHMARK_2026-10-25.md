# Smart Verification V2 measured evidence — 25 October 2026

## Comparable scheduling experiment

GitHub Actions run: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796618

Reference job: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796618/job/121107016062

Parallel job: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796618/job/121107015923

Both jobs used commit `62897984c07e1ee634b95fa08f37669e4c1f1ec4`, tree `02386a3ec0640e93f9e61d845fc572c69819b0c8`, the same 217 Python tests and 25 Node tests, no failed/skipped/TODO cases, and identical workflow, inventory and dependency/environment fingerprints. The only intended difference was command scheduling: one worker versus four. This compares equivalent feedback workloads, not full acceptance versus smoke.

| Metric | Sequential reference | Parallel candidate | Observed reduction |
| --- | ---: | ---: | ---: |
| Coordinator execution | 69.24 s | 39.75 s | 29.49 s / 42.6% |
| Actions execution step (rounded API timestamps) | 71 s | 51 s | 20 s / 28.2% |
| Complete worker job, setup/artifacts included | 95 s | 70 s | 25 s / 26.3% |
| Runner consumption for this workload | 1.583 min | 1.167 min | 0.417 min / 26.3% |
| Executed Python / Node cases | 217 / 25 | 217 / 25 | No reduction |

Immutable artifact IDs: sequential `12591336238`, parallel `12590609013`; the Actions artifact metadata includes their ZIP SHA256 digests. These are observations from one pair, not a causal estimate or guaranteed future saving. The jobs ran at different times on GitHub-hosted Ubuntu workers; queue delays and noisy neighbors can differ. Both first-run reports flagged historical checkout line-ending differences as dirty. They are timing observations only, not clean-tree certification; the final workflow now restores the exact historical tracked bytes before fingerprinting. Automatic artifact reuse remains disabled.

## Acceptance and unavailable measurements

Canonical full acceptance run: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796484

Fast feedback run: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796432

| Requested metric | Baseline | Observed V2 result | Interpretation |
| --- | --- | --- | --- |
| Full PR fast job latency | No equivalent V1 workload retained | 158 s worker time | No V1 percentage claimed |
| Stable-feature full acceptance | No equivalent previous test inventory | 34 m 53 s wall time; 47.067 runner-minutes | Linux + Windows + aggregate PASS at the recorded SHA; no causal speedup claimed |
| Full integration wall time | Not available | BLOCKED | Four-stream conflict; no tested combined candidate |
| Total complete-PR runner usage | Not reconstructed for equivalent old/new event sets | Not claimed | The scheduling experiment above is a narrower measured runner comparison |
| Repeated complete test matrices | Historical independent workflows retained | Canonical full regression remains one authority per OS for ready PRs | Focused feature/fixture-order safety repeats are intentional and remain |
| Android build/setup time | Not available | NOT VERIFIED | Main-based verifier tree contains no Android application sources |
| Required check coverage | Existing canonical contracts | Retained | Fast green never substitutes for mandatory full/installed/private/device gates |

Linux worker: 759 s; Windows worker: 2,062 s; aggregate job: 3 s. Sum = 2,824 s (47.067 runner-minutes), distinct from wall time. These are execution durations, not billed-price estimates.

Live four-stream preview: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/40172796529

It failed explicitly on a real merge conflict while retaining the resolved manifest artifact. This is expected blocked integration evidence, not a verifier test failure or a successful combined release. A source branch advanced while the workflow ran; the manifest captured its new live SHA, demonstrating that branch heads are resolved rather than permanently hardcoded.

Subsequent commits must rerun their own checks. The measurements and successful acceptance above certify only the source identity named above; they do not certify later source changes or the unmerged four-feature Android tree.
