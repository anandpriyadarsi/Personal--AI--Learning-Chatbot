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

Native screenshot review found a false host-loss banner: older API31 WebView has
no AbortSignal.timeout. Reproduced in real Chromium with that API removed (RED),
replaced with compatible AbortController, then22 focused HTTP/runtime/backup/
compatibility cases GREEN. Native smoke now waits for a healthy local response.
Screenshot collection waits for WebView visual-state completion and two actual
compositor frames, avoiding the first secure-window blank capture.

29 Node cases pass after the compatibility change. Full local regression remains
in progress and has reported a failure; no whole-suite success is claimed.
Native Ubuntu/Windows jobs must report their own exact-source results.

Continuation, 23 October: resumed published aa92836 on the same dedicated branch.
Latest prior native run39883294392 passed Android build/JVM, API31 offline
Notes/Planner force-stop, and Ubuntu (2,958 tests; four external IKS skips).
Windows failed three V1.5 browser cases; parallel UI/Library runs failed the
same journey. Root cause: the async cross-owner link waits for queued writes,
but the assertion matched `1 of 31` on the OLD practice page before navigation.
The test then raced a second goto/screenshot. Wait for the exact quality URL
and heading before the unchanged evidence/print assertions. No retries, skipped
cases, timeouts, production policy changes or snapshot weakening.

Local focused result: all16 V1.5/V2.4 Chromium cases PASS; all14 runtime/backup/
synthetic-bundle cases PASS; all29 Node cases PASS. Browser install initially
unavailable; after installation the actual headless browser runs normally.
Full local/native regressions remain pending until their outputs arrive.

Added synthetic-only instrumentation assets via a host-generated backup. The
test APK, not the installable app APK, owns the fixture. It imports approved
online/paper packages through production owners, publishes a source-linked
lesson, and starts with paused sessions. Expanded native gate covers active
lesson/mistake/Library reading, real native confirmation Cancel/OK, assessment
question2 answer + explicit Pause -> force-stop + same-key reinstall -> frozen
clock + same question/answer Resume, paper step-review persistence and rotation.
Those new native cases are pending execution; no pass is inferred from code.

Run39911547434 at36d57b7 passed Android build/JVM and the expanded API31
emulator journey: both instrumentation phases passed (23.188s and12.107s),
including genuine native confirmation Cancel/OK, lesson attempt, original
Library text, paper step review, frozen question2/answer after force-stop and
same-key package replacement, Resume and landscape/portrait rotation.

Independent final review found two Important defects. DownloadListener gave all
attachments a ZIP name/MIME; a pure-Java regression failed2, then passed2 after
bounded filename/MIME preservation (existing origin test also passes). Android
conversion routes exposed a desktop subprocess-only parser; production source/
publish test failed, then passed after explicit Android capability UI/422 gates.
Local PDF ingestion/text extraction and authored-package reading still work.
Reviewer rechecked both fixes and independently passed the modified runtime
case; no Critical/Important issue remains in those fixes. Native attachment
tests now inspect the actual SAF intent for PDF/TXT/ZIP then cancel it; external
document-provider byte writing remains an owner-device/manual integration gate.

Run39912295954 built the review-fixed APK/JVM successfully. Its emulator passed
all three real WebView -> SAF attachment-name/type checks, then the first
confirmation assertion failed: mutation reload status was visible before the
deferred form handler finished attaching. The test now waits for completed
document readiness at every live-state boundary before clicking; it keeps the
same real Cancel/OK assertions. No fixed delay or retry was added. PR updates
alone trigger the Android workflow now; the duplicate push hook was removed
without deleting any build/test job or case. Native rerun remains required.
