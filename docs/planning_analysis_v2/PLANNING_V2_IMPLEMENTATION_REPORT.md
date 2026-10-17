# Planning V2 implementation

Implemented a responsive dark Planning hub with day/week/month commitment timeline, today status, course-filtered task inbox, due/preferred date/effort labels, weekly review and month-import links. Calendar due markers are labelled as due dates, never allocated study sessions. Approved study sessions remain in the canonical day view; the month timeline does not claim to contain those slots. No inferred free capacity is shown.

The day page accepts explicit availability via GET preview, then a deliberate protected save-draft POST, then separate protected approval. Drafts show saved times. Preview hides completion/close actions; approved/active items expose existing execution actions. Browser journeys record actual effort and save weekly reflection through existing owners.

## Placement

Only explicit date-keyed windows, clamped to 06:00–22:10 and current local time, are considered. Fixed commitments subtract buffered intervals. Missing duration/all-day commitments, past days, uncertain offset events and DST-transition days fail closed. Flexible tasks require valid duration, no hard deadline already passed and no placement before preferred date. Maximum five candidate tasks, shared deep-work ceiling (three; one on a busy day), ten-minute breaks. Study and inbox tasks share one deterministic priority order, windows and ceiling. Saved date-specific study is P1 due-today work; P0 tasks rank before it. This is scheduling policy, not inferred academic urgency.

Recurring COUNT is anchored to the original series, exclusions do not reset sequence, recurring events remain discoverable beyond original end. Multiday spillovers block occupied days. Offset-bearing commitments conservatively block the source date ±2 days because the old calendar contract has no canonical timezone; safe but overconservative.

Save/approval validate source fingerprints transactionally. Approval rechecks task/study duration, current clock, deadline/preference, overlaps and buffers. Timezone defaults match the academic overview. A changed task/event/source or elapsed slot requires fresh preview. No production migration, automatic task creation or auto-approved reschedule.

Remaining: persistent availability/versioned scheduling policy; alternatives generation; approved sessions in week/month; original-window validation at later approval; explicit accepted carry-forward (P03); changed month revision ledger repair (P06); canonical study completion/engagement linkage (P08); richer weekly workload by course. Existing close-day behavior creates a tomorrow draft and has known drop-policy defects; it remains a documented legacy flow rather than a verified V2 replan. Do not use that flow as S8 acceptance.
