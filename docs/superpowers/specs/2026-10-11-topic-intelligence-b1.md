# B1 closed-snapshot Topic Intelligence specification

Approved by the user's ANVAYA_NEXT_WORK_MASTER_PROMPT: after actual hosted Gate A Ubuntu/Windows acceptance, implement the smallest separately scoped source-only B1 reader. No repeat design approval is required.

Base: 710b249d575f18fcd720772b9c7393bdc7ea8f52. Gate A run38129594236 is accepted on both platforms. Production authority is separately BLOCKED.

Use frozen dataclasses and one SQLite repository accepting an explicit closed/checkpointed artifact, canonical course/topic IDs and an aware as_of datetime. Default configured timezone Asia/Kolkata. No default DB, live connection, copying, migrations, provider, consumers, route/UI integration, JSON fallback or authority initialization.

Preserve signed integer milli-marks, statuses, exact source IDs and grading confidence. Mapping and independence remain unknown; current mutable mappings, author confidence and exam mode cannot establish historical trust. Every B1 observation remains automatically ineligible. Self-entered outcomes carry a supporting/self-reported exclusion. Stored manual status is not assessed mastery. Empty evidence is unknown coverage, not zero mastery.

One response evaluation produces one observation. Attempt/mistake bridges remain references, never extra observations. Preserve provisional/deleted/cross-course/inconsistent sources with exclusions; reject missing parent records or malformed score storage with typed errors. Duplicate content hashes normalize Unicode and whitespace but preserve question type/options; original IDs remain separate. No answer key, solution, learner response text or local path enters the DTO.

Read-only immutable mode requires caller attestation of a closed artifact. Reject symlink paths and SQLite sidecars, check stat/digest before and after, close the query-only transaction. These checks detect observable changes but do not prove absence of writers. Never use this API against the live application DB.

Regression scope includes immutable structures, signed marks, unknown provenance, duplicates, exact/deleted/cross-course identity, inconsistent bridges, malformed/future/naive timestamps and conversion overflow, noninteger SQLite values, file/SQL/checksum invariance, real WAL refusal, missing schema/file and changed snapshot detection. Full unchanged validator, independent review and actual hosted Ubuntu/Windows acceptance are required.

Full Gate B still needs the separately owned read-safety and immutable attribution contracts. C/D/E and Assessment pause/paper implementations remain outside B1.
