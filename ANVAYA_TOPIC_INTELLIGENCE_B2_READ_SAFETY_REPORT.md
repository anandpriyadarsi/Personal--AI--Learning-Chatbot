# ANVAYA Gate B2 read-safety implementation

Starting B1: `6d2c3a01d6deca5b64bfc19ce2041769a8b00929`, branch `anvaya/topic-intelligence-b1-readonly`. B2 branch: `anvaya/topic-intelligence-b2-read-safety`. Main independently fetched at `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`. Published B1 and hosted run38201393653 were verified; uploaded evidence SHA256 manifest and platform summaries match B1. GitHub implementation was used directly, with no patch/bundle applied.

## Reproduction and minimum correction

Actual `/planning` → planning dashboard → academic progress topic ranking → get_course_memory → load_memory called ensure_memory_file. `/analysis` → Home academic brief → academic priority/risk → the same load similarly initialized the store. The B1 child probe reproduced creation of learning_memory.json in both seeded cases and a write to its .tmp file; empty cases were unchanged. This is defect C, not a simulated provider failure.

- `learning_memory.py::load_memory` now reads existing authority, returns fresh empty defaults for an absent legacy file, and raises a safe error for corrupt/nonobject/unreadable existing memory. It never calls ensure/save. Existing valid V7/V8 data is normalized only in memory; bytes are unchanged. Explicit ensure_memory_file and save_memory remain initialization/write commands.
- `course_manager.py::load_course_data` likewise no longer calls its explicit initializer. It and the actual `repositories/json/course_repository.py::load_state` used by CourseService now reject corrupt/nonobject/unreadable course sources instead of presenting them as a normal empty catalogue. This closes the neighboring direct compatibility loader's missing-source side effect. Existing CourseService/JSON repository ownership is retained.
- `repositories/structured_authority_router.py` now separates existing runtime read connections (`mode=ro`, `PRAGMA query_only=ON`) from existing command connections (`mode=rw`). No database path, authority switch, schema or projection seed is introduced. Commands retain their prior guards and transactions. Corrupt/missing promoted DB/projection/control raises; it never silently falls back to legacy JSON.

Live runtime reads remain WAL-aware. They may create empty WAL/SHM SQLite coordination artifacts on a WAL-mode database; those are explicitly reported separately from logical writes. B2 tests require unchanged database/JSON hashes, unchanged SQL dump, no SQL mutation attempts, no migrations/seeds/index/session/authority creation. DELETE-journal disposable fixtures additionally prove exact file invariance. B1's caller-attested closed immutable reader remains distinct: concurrent reads preserve exact inventory and reject active sidecars.

## Regression proof and characterization transition

Desired tests ran before product edits:8 failed and8 passed. Failures included both seeded GETs, corrupt memory fallback, direct missing loaders and absent query-only enforcement. The first canonical test incorrectly demanded sidecar-free live reads; investigation established the SQLite coordination distinction, so it was replaced with stronger SQL authorizer/dump/hash assertions and explicit sidecar classification. No sidecar deletion/cleanup command was added to production reads.

Expanded B2 tests cover12 real route/state combinations with three requests each (empty, seeded, valid legacy bytes, corrupt memory, corrupt courses, promoted canonical), explicit initialization, corrupt UTF8/JSON/nonobject memory, query-only write refusal, committed WAL visibility, corrupt/missing authoritative DB/control/projection without fallback, repeat planner previews and8 concurrent B1 reads. The original45 B1 cases, DTO and repository remain byte-identical; all14 migration SQL files remain byte-identical.

C's inverted read_routes and planning loader assertions are replaced by desired no-initialization acceptance only after the owning regression passes. The read_routes probe uses the existing tracked-source exporter so precommit tests inspect the current reviewed source instead of archiving stale HEAD. C has its own desired test outside the known-defect parametrization; it is not skipped or deleted. A (strong-topic recovery), B (future preferred day), D (unknown historical snapshot) and P01–P08 assertions retain their exact meanings and remain unresolved product defects. Validator records C PASS only when the characterization category passes.

Four real Chromium tests exercise actual default Planning/Analysis routes at390,768,1366,1920 px, reload, overflow and keyboard navigation while checking file preservation. Initial test-only focus failures were resolved by opening the responsive navigation and More disclosure before focusing its hidden link. Product UI is unchanged.

## Limits

B2 implements this source-only read-safety boundary. It does not complete all Gate B attribution/writer/projection work, add live B1 consumers, repair recovery/Analysis/Planning policy, or implement Assessment pause/paper self-evaluation. Missing memory gives empty supporting evidence, not a mastery score; the existing legacy progress UI remains outside Analysis2.0 scope. Historical mapping/independence and self-entered outcome exclusions remain unchanged. Production authority remains BLOCKED. No migration, paid provider, production academic write, main merge or deployment was performed.

## Independent review closure

Review reproduced the corrupt legacy-course gap after the first bounded fix and an existing symlink-parent alias bypass. Nine additional regressions failed before correction (29 passed). Legacy memory/course readers and canonical runtime read paths now reject symlink components, including parent aliases; command-path semantics are unchanged. Missing files remain defaults and valid legacy bytes remain unchanged. The browser locator issue was corrected and independently retested. The handoff now explicitly blocks Gate C implementation on full B contracts and separate authorization. Final reviewer outcome is recorded after the stabilized repair.

Final independent review:169 affected cases PASS, zero failures/errors/skips; no open Critical/Important findings. The additional routed courses.json symlink and dangling authority-control bypass each had a failing regression before read-only store/control guards were added. These guards preserve genuine missing-control legacy behavior. Supporting progress-history and other legacy plan-store corruption semantics remain separate bounded issues; this report does not claim a platform-wide corruption-policy refactor.
