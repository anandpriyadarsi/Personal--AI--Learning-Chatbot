# PAO weekly evidence and reviewed actions

Implemented on the shared PAO feature branch, 12 November 2026. No merge or activation is claimed.

## Evidence behavior

Weekly Review and Analysis share one read adapter. Scheduled effort includes task/study/manual occurrences with a parseable approval instant and valid allocated interval, excluding fixed/routine items and reasoned pre-start moved/skipped occurrences. Unallocated estimates are separate. An empty healthy plan is zero scheduled minutes; missing actual time remains null and explicit zero remains zero. Logging coverage is a numerator/denominator and 0/0 says no eligible sessions.

Explicit work logs replace their derived agenda actual value, and append-only corrections supersede the original only when their occurrence is at or before the requested as-of instant. Independent partial logs sum once. Deadline outcomes query due tasks independently of agenda existence, use the supplied aware clock and local end of day, and separate on-time, late, unresolved, upcoming and unknown. Contradictory status/completion timestamps are unknown. Distinct completed tasks require dated terminal command receipts. No effort or completion result implies mastery.

The metric envelope includes scope, timezone, as-of, policy, status, source identities and exclusions. Upcoming workload reports known estimated minutes and counts tasks lacking estimates. Revision queue and week comparison are explicitly unavailable when a qualifying owner/comparable snapshots are absent. Assessment outcomes retain individual denominators and prominently disclose bounded source sampling. Task totals query the whole matching population independently of the priority-ordered display page.

Closed reviews persist the displayed metrics JSON, fingerprint, policy and as-of in optional 0018 columns; subsequent reads use that immutable JSON. Legacy closed reviews retain their historical integer values and say coverage unavailable rather than reconstructing history. Form submissions carry review revision and evidence fingerprint; the repository rechecks fingerprint inside its immediate transaction. GETs never migrate. Closing with missing provenance columns fails with an unavailable response rather than storing a false snapshot.

## Action behavior

At most three deterministic suggestions link exact overdue commitments. Qualified topic/revision adapters require confirmed mapping; unreviewed or missing mappings never become inferred weakness/mastery. The explicit revision adapter only considers current sources with a user-entered due review date. Exact Learning sources remain available through the existing evidence index when no reviewed suggestion exists.

The existing manual-study preview now lets the learner edit title, estimated minutes and optional due date while showing exact module revision, source hash, course and topic. Its signed intent and existing source fingerprint are revalidated before the existing task owner writes. Identical double-clicks return one task; changed payload on the same intent conflicts. Grades, attempts, provider consent and original source bytes retain their existing owners. No automatic task creation or provider call is added.

## Verification

RED first: two new weekly regressions reproduced missing as-of support/no-agenda deadline undercount and counting unapproved/unallocated closed-draft effort. A separate preview regression reproduced absent editable fields before implementation. Existing fixtures were made explicitly approved and allocated rather than preserving their contradictory old assumptions.

Final verification command:

```bash
python -m pytest -q tests/test_pao_weekly_metrics.py tests/test_pao_study_actions.py tests/test_phase7_5_weekly_review.py tests/test_planning_analysis_v2.py tests/test_planning_v21_wal_snapshot.py tests/test_academic_evidence_v23.py tests/test_academic_evidence_v23_web.py
```

Result: **85 passed in 12.58 seconds**, no skips.

Includes null/zero, correction dedupe and future corrections, historical deadlines, snapshot immutability/staleness, priority-skewed task totals, mixed >100-session sampling, exact action links, edited source preview, same-intent retry/conflict, source/mapping changes, independent grading, read invariance and WAL snapshot boundaries.

Earlier broader run: 42 passed, 3 existing proposal journey failures because those tests submitted without the newly required PAO command token. The command-boundary owner is updating those fixtures. A transient ordinary/optional migration placement conflict during concurrent implementation was resolved before final verification; it is not a skipped test.

## Limits and remaining acceptance

Browser/zoom/physical-device checks and Windows validation are owned by the parent integration pass and are not claimed here. Revision queues with persistent explicit source-review dates, compatible adjacent-week comparisons and a complete cross-owner source-to-action catalogue remain honestly unavailable in this projection. Assessment sampling is explicit rather than represented as complete history. Qualified recheck suggestions remain blocked for current unreviewed topic mappings. The new metrics do not establish independent academic performance.
