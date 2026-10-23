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

Real CI API31 emulator (run39881026047) built/installed both APKs, then reproduced
startup rejection of Android's platform-owned filesDir alias. Fixed at native
trust boundary by passing Context.filesDir.getCanonicalPath(); Python still
rejects arbitrary symlink roots. Native retest required. The installed app did
not reach main in that run; it is not a successful standalone certificate.

Actual authenticated Chromium native-runtime journey exposed a settings template
syntax defect. Reproduced native and original PWA contracts RED, corrected title
block, then 21 tests GREEN. Eight actual runtime pages, Notes create/reload,
HttpOnly capability invisibility, zero service workers and zero external requests
passed in Chromium134. Screenshots are browser evidence, not Android evidence.

Android12 API31 x86_64 real installed-app gate PASSED at remote957475699919f93396c7bd83d3723fcb5db888c4,
Actions39881936564: two instrumentation phases (9.741s and5.193s), Wi-Fi/mobile
data off, real Notes form → force-stop → reopen → same note. Actual emulator
screenshots captured; physical Samsung certification remains blocked.

The same-source Android build/JVM job passed. Expanded native lifecycle adds a
production Planner SQLite task to the force-stop/reopen check (cloud process
write/new-process/read already passes). Final Android run must prove this too.

Self-review found overview navigation was incorrectly waiting on an undefined
bookmark result. Reproduced actual browser failure, made no-write views return
successful no-op, then all seven V2.4 live browser cases passed. No academic
snapshot guard was weakened. Full Ubuntu/Windows gates remain separate.
