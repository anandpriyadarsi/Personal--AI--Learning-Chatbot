# Implementation ledger

Owner provided complete design/acceptance specification and explicitly authorized
implementation without another design approval. Fresh isolated clone on dedicated
branch. Existing checkout changes to backup.py/dashboard.py (EOL only) and brand
PNG are left untouched and excluded from commits.

Task 1: in progress — runtime/bootstrap/security tests, Android build toolchain.

Runtime/backup increment: 13 new production-process/backup cases pass. Real Notes
save/reopen, source registration/extraction, course setup, published lesson
rendering and SQLite archive export run against production owners. 29 Node
contracts pass. Reading-save navigation reproduced with held POST, then passed
with serialized saves/navigation. Protected academic inventory now selects DB
paths before opening any unrelated journal.

Initial APK: assembled successfully, ~51 MiB with embedded Python 3.11 and Pillow
11.0 Android wheels (armv7/arm64/x86_64). JVM exact-origin case passed. Native
emulator/instrumentation still in progress; compilation is not device acceptance.

Review: independent reviewer found request-envelope size mismatch and incompatible
schema restore could prevent startup. Both reproduced RED; envelope increased to
101 MiB for a 100 MiB archive, production owners validate restore copies before
replacement. 13 cases GREEN. No re-review certificate claimed. Runtime startup
also serialized; Activity is singleTask to avoid duplicate embedded launchers.

Ruling: this first package blocks all online AI/external Python networking; an
incomplete consent flow must not send records. Cost: online AI unavailable in this
increment. This is an explicit compatibility limitation, not an LLM certificate.
