# Smart Verification V2 implementation plan

Goal: implement the user's supplied V2 specification on existing PR #53 without changing feature branches or main.

Architecture: preserve the V1 CLI, add an explicit component dependency graph, use one fast orchestration workflow and the canonical architecture validator for stable/full acceptance. Evidence is exact-tree and environment scoped; JSON alone grants no certification. Integration resolution is read-only; previews write Git objects only, never refs.

## Constraints

- No application business logic, production records, feature branch rewrites, main merge or APK release.
- Unknown paths, missing inventories and unreliable diffs require broad validation.
- No private material or credentials in caches, logs or artifacts.
- Physical phone/private fixture/emulator absence remains BLOCKED.

## Tasks

- [ ] Add failing dependency selection, evidence, integration Git-DAG and failure diagnosis tests; prove RED.
- [ ] Implement policy and coordinator, preserving V1 compatibility; prove GREEN.
- [ ] Resolve live stream manifest, detect overlaps/stacking, preview merges without branch mutations.
- [ ] Consolidate fast checks and canonical acceptance reuse; retain stable acceptance names, strict aggregate gates and protected release limitations.
- [ ] Run selector, Node, full Python/browser checks available locally and exact-head GitHub CI; collect comparable Actions timings.
- [ ] Review complete diff, record limitations, update PR #53 and keep unmerged.

## Review focus

Deleted/renamed tests; unavailable merge-base; stale evidence for a different merged tree; fork cache writes and secrets; cancelled/skipped mandatory checks; stacked Android ancestry; unrelated files mistaken for documentation.

## Execution ledger

- Verified main at 2c4fa151768f20e6e37e99c2fb1d1e8460247e46. Existing V2 PR #53 head e5c85b0; reused dedicated branch and merged main into it without changing main or feature branches.
- Fresh checkout has historical CRLF differences in backup.py/dashboard.py. Existing architecture_checkout_eol.py restored their exact tracked bytes; neither application file is part of this change.
- User supplied detailed implementation specification and explicit continuous execution authority; proceed without another design approval round.
