# Durable explicit capacity

With PAO activated, proposal metadata and canonical draft items commit in the same SQLite transaction. The record retains user windows, derived UTC bounds, policy/break settings, candidate/source context, semantic/source hashes, nonce and command identity. Reopening after process restart reads this record and signs a fresh approval. A changed relevant source suppresses approval until re-preview; unrelated future commitments and prior review history do not invalidate the draft.

Native forms support multiple availability windows. Overlapping/invalid/elapsed windows and ambiguous local times fail validation. Fixed commitments are subtracted first; unknown occupancy prevents an invented placement. The scheduler searches feasible candidates before imposing the cap and retains a reason-coded review queue; overdue deadlines are never silently moved. Duplicate draft save returns the existing intent; duplicate approval is a safe409 with no second mutation.

Feature-off retains the prior session-only proposal behavior and labels that limitation. Optional storage is never created on GET/startup. Regression cases include restart/reopen, overlap/elapsed bounds, blocked first five versus feasible sixth, small task behind a larger task, unknown fixed occupancy, relevant/unrelated changes, duplicate save/approve and context-write rollback.
