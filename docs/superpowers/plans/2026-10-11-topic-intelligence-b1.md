# B1 read-only Topic Intelligence implementation plan

Use superpowers:executing-plans inline. The user's master prompt approves the smallest compatible source-only design. Independent final review required.

Goal: immutable DTOs and one explicit closed-snapshot reader without migration or consumers. Tech: existing dataclasses, datetime/zoneinfo, hashlib, sqlite3, pytest. No new dependency.

- [x] Verify hosted Gate A Ubuntu/Windows acceptance at exact base710b249d (run38129594236).
- [x] Write synthetic tests and observe missing adapter RED before original implementation.
- [x] Implement immutable observations, exact identity, read-only closed snapshot boundary, explicit unknown provenance and deterministic fingerprint.
- [x] Add file/SQL safety and trust regressions; original B1 suite34 passed.
- [x] Independent review and repair: four Important findings;11 new regression cases RED before repair;45 B1 and65 B1+Phase E/F GREEN afterward. Reviewer confirmed no remaining Important/Critical findings.
- [x] Full unchanged validator and recovery review after workspace maintenance: run-ffjibcku,1817 full/39 browser; all15 categories PASS; independent65 focused PASS.
- [ ] Commit/publish dedicated feature branch and inspect actual hosted results.
- [ ] Deliver exact SHA, evidence and Windows handoff; do not claim fullB or production authority.

On12 October automated workspace maintenance removed the uncommitted worktree and unfinished full validation. Gate A was recovered from GitHub at the exact base. B1 source and all45 tests were reconstructed from conversation-preserved code and fixes. One additional assertion checks that a valid bridge is not flagged; no intended behavior change. Fresh validation/review is required; interrupted runs are not acceptance evidence.

Constraints: no production data, migration allocation, legacy GET modification, runtime integration, recovery policy, old branch merge or main merge. Preserve Assessment/Coding Helper and unrelated Learning Studio/Tutor work.
