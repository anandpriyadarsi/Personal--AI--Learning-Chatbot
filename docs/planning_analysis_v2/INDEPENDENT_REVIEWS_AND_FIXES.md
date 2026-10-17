# Independent reviews and fixes

Independent agents reviewed four user-requested domains. Findings were checked against code and reproduced with disposable fixtures. No reviewer approved production authority or a main merge.

| Domain | Finding | Reproduction / resolution |
|---|---|---|
| authority/security | read-only SQLite changed live SHM; partial self-score looked complete; future response leaked into scored result | review-red.log: three failing tests; strict WAL refusal, complete-denominator and dated-response guards; tests/test_planning_analysis_v2.py |
| scheduling | timezone mismatch, recurring/multiday/offset collisions, stale approval, lost saved slot display | targeted negative tests, shared local timezone, fail-closed occupancy, anchored recurrence, current source and transactional approval guard, day_view uses saved rows |
| Learning/Assessment compatibility | paper self-reviews absent / malformed snapshots / draft and future revisions misattributed | bounded submitted-revision projection, snapshot provenance/identity/denominator checks; 22 projection/authority tests at review checkpoint |
| UX/accessibility | preview showed execution controls, topic observations unreachable, unavailable effort rendered 0/0, saved times invisible | ui-review-red.log: three failures; explicit preview state, topic source cards, unknown coverage, saved-slot rendering; four review regressions |
| final scheduling | saved study plus task capacity duplicated; obsolete probes still expected repaired defects | capacity-red.log; shared windows/deep limit, desired characterization assertions; fresh independent scheduling review of final changes |

No generic human approval was fabricated. Initial authority review was interrupted after concrete findings; its findings were reproduced, but it did not complete a whole-branch final review. Compatibility owner caveat: completed paper canonical delegation can still reach an extended-workspace 404 in a legacy fixture. This remains an owner integration blocker. UX minor issue (Assessment filters in task inbox) was resolved by retaining only the course control on Planning.

Remaining important concerns: full-route physical WAL invariance; historical mapping/independence; original availability not persisted; P03/P06/P08 legacy integration. Final independent scheduling review also reproduced P1 saved study starving a due P0 task; a RED→GREEN regression now enforces the common priority order. See final scheduling review evidence in the archive and acceptance report for executed counts, not this checkpoint narrative.
