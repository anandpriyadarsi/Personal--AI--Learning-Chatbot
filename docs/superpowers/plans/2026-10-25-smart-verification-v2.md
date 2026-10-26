# Smart Verification V2 implementation plan

Goal: implement the user's supplied V2 specification on existing PR #53 without changing feature branches or main.

Architecture: preserve the V1 CLI, add an explicit component dependency graph, use one fast orchestration workflow and the canonical architecture validator for stable/full acceptance. Evidence is exact-tree and environment scoped; JSON alone grants no certification. Integration resolution is read-only; previews write Git objects only, never refs.

## Constraints

- No application business logic, production records, feature branch rewrites, main merge or APK release.
- Unknown paths, missing inventories and unreliable diffs require broad validation.
- No private material or credentials in caches, logs or artifacts.
- Physical phone/private fixture/emulator absence remains BLOCKED.

## Tasks

- [x] Add failing dependency selection, evidence, integration Git-DAG and failure diagnosis tests; prove RED.
- [x] Implement policy and coordinator, preserving V1 compatibility; prove GREEN.
- [x] Resolve live stream manifest, detect overlaps/stacking, preview merges without branch mutations.
- [x] Consolidate fast checks and canonical acceptance reuse; retain stable acceptance names, strict aggregate gates and protected release limitations.
- [x] Run selector, Node and full Python/browser checks through exact-head GitHub CI; collect comparable Actions timings. Final follow-up commit must receive its own CI. The interrupted local full run is not claimed as complete.
- [x] Review complete diff, record limitations, update PR #53 and keep unmerged.

## Review focus

Deleted/renamed tests; unavailable merge-base; stale evidence for a different merged tree; fork cache writes and secrets; cancelled/skipped mandatory checks; stacked Android ancestry; unrelated files mistaken for documentation.

## Execution ledger

- Verified main at 2c4fa151768f20e6e37e99c2fb1d1e8460247e46. Existing V2 PR #53 head e5c85b0; reused dedicated branch and merged main into it without changing main or feature branches.
- Fresh checkout has historical CRLF differences in backup.py/dashboard.py. Existing architecture_checkout_eol.py restored their exact tracked bytes; neither application file is part of this change.
- User supplied detailed implementation specification and explicit continuous execution authority; proceed without another design approval round.
- Independent review identified skipped-Node false passes, deleted JS omissions, incomplete live resolution and a missing native PR caller. Each has a reproducing regression and verified correction. Final author audit added changed-JS syntax checks, named conflict paths and untracked-source evidence guards.
- Ruling: automatic remote evidence reuse stays disabled until authenticated immutable artifact provenance is provisioned. Cost: repeated external runs remain necessary; benefit: no stale/user-editable JSON can certify a candidate.
- Ruling: stable-feature acceptance retains a conservative full canonical superset and existing focused contracts. Cost: stable candidates still incur broad Linux/Windows regression; ordinary draft feedback remains scoped.
- Deferred minor: pip dependency cache writes retain GitHub's PR-ref isolation; browser cache saves and Gradle cache writes have explicit trusted-branch restrictions. No credentials or private fixtures are cached.
- GitHub first implementation checks passed fast, canonical full Linux/Windows, Assessment, Tutor, UI, Library, reader and intelligence. Integration manifest correctly FAILED on the existing feature-stream conflict. No feature branches or main were modified.
