# Unified ANVAYA integration history — 26 October 2026

This ledger was recorded before the main merge. Candidate/pending states below describe that point in the integration; the versioned GitHub release and its BUILD.json are authoritative for the delivered main SHA, installed checks and APK metadata. Earlier feature APKs are not final-release evidence.

## Provenance and disposition

Initial main: `40ef6a76caf1ccaf023a705f4f7d584dd8c02915`. All 20 initially open PRs were inspected, plus new Focus Reading PR57. `MATRIX.json` preserves every source head, base, URL and disposition. Related active branches and their latest commits were inspected; the current main reader/full-view repair is retained.

| PR | Development | Candidate disposition |
|---|---|---|
| [#55](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/55) | Smart Notes: nested sections, universal attachments, optional Obsidian and light Android startup | Retained through source merge |
| [#53](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/53) | Smart Verification V2: dependency graph, shared CI and safe integration coordination | Retained through source merge |
| [#52](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/52) | Android CBT: post-test review, answer feedback and standalone question quality gate | Retained through source merge |
| [#51](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/51) | Android candidate: original-document Library, safe sharing and PDF match-page reader | Retained through source merge |
| [#50](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/50) | Library: preserve original documents and search matching PDF pages / PPTX slides | Retained through source merge |
| [#49](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/49) | Android V1.1.3 test: fast reader navigation, mobile fullscreen and Library rename | Retained through source merge |
| [#47](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/47) | Handwritten Notes: persistent audio/video attachments and Android external-player opening | Retained through source merge |
| [#45](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/45) | Learning Studio: mobile visual reader, usable fullscreen fallback, subject mapping | Retained through source merge |
| [#44](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/44) | Android: speed up offline page navigation with private asset caching and parallel static loads | Retained through source merge |
| [#43](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/43) | Android: restore Assessment subject options and import source-bound UC103N Vedic Work ZIP | Retained through source merge |
| [#42](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/42) | Unified standalone Android V1.1.2: current academics, Tutor, Assessment and Library | Retained through source merge |
| [#41](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/41) | Android V1.1: same unified Library / Knowledge interface (no data migration) | Retained through source merge |
| [#39](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/39) | Mobile Assessment: clear CBT and handwritten modes, safe pause and rubric review | Retained through source merge |
| [#38](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/38) | Tutor UI V3: chat-first mobile redesign integrated with standalone Android | Retained through source merge |
| [#35](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/35) | Mobile V1.1: standalone private Android test APK and offline academic persistence | Retained through source merge |
| [#34](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/34) | ANVAYA Mobile V1.0 — Private Android-First Learning Companion | Retained through source merge |
| [#29](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/29) | Integration preview: Architecture V2.2 + Library and Resources V2 | Superseded by newer implementation; source preserved |
| [#27](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/27) | Architecture V2.2: private pilot validation and academic safety corrections | Superseded by newer implementation; source preserved |
| [#13](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/13) | B3 read-only identity inspector: accept exact namespaced assessment evaluation refs | Retained through source merge |
| [#9](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/9) | Gate C0: conservative read-only recovery-policy simulation with adversarial tests | Retained through source merge |
| [#57](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/57) | Focus Reading: show complete notes and read-only media only | Retained through source merge |

## Combined behavior

- Current main navigation, responsive Learning Studio, fullscreen feedback, reviewed subject mapping and persistent document display names.
- Standalone embedded-Python Android stack, canonical subject setup, source-bound authored imports, Tutor UI and existing Coding Helper.
- Typed/handwritten notes with nested sections and universal attachments; Focus Reading expands complete content and hides editing/attachment controls.
- Optional Obsidian Markdown ZIP snapshot browsing, search, backlinks and explicit independent copies. No live sync or direct Android folder access is claimed.
- Original PDF/PPT/PPTX document storage, background page/slide indexing, file management, native PDF page reader and external document sharing/opening.
- Submitted Assessment results/review, red wrong answers/green correct answers, explanations, pause/resume and generated self-contained question validation.
- Shared Verification V2 graph, exact-input evidence, mandatory canonical checks and build-once API31/API35 installed acceptance.
- B3 read-only identity/provenance inspector and synthetic-only C0 recovery simulation. This does not grant production academic attribution or automatic task authority.

## Integration repairs

- Reconciled Android startup, fullscreen Back, Library viewer, media providers and route registration rather than choosing one branch wholesale.
- Preserved records-only backup API while taking both notes and original-Library storage locks. A concurrent-delete regression reproduced a missing-attachment archive before the fix.
- Screenshot diagnosed actual `net::ERR_UPLOAD_FILE_CHANGED` at `/library/upload`. Native picker now makes bounded immutable private copies, retains Unicode filenames and extension, and returns read-only app URIs to WebView. The copy test checks stable bytes, isolation, quota/error cleanup and stream closure. Installed test uses a timestamp-changing external provider and an actual WebView multipart upload.
- PDF viewer and external media result codes no longer alias.
- Newer owner-selected static black splash replaces the earlier animation; tagline is `Personal Learning Intelligence...`. Startup still waits only for the first rendered workspace frame.
- Version `1.2.0-unified-debug`, code `16`; app Settings shows the compiled Git SHA. Gradle obtains that SHA from the checkout itself.
- Windows CI exposed a read-handle/atomic-replace race during parallel attachment saves (149 passed, 1 failed). Added a deterministic sharing-violation regression, watched it fail, and serialized note reads with the same repository lock as writes. The 62-case notes/media/nested/runtime selection then passed locally; Windows exact-source rerun remains required.
- Fixed the legacy manifest test to select MainActivity explicitly now that the app also contains PdfPageActivity.
- Removed redundant ready-PR APK/emulator builds from the legacy mobile caller while retaining shared exact-source installed checks and focused browser regressions.
- Windows B3 identity check now uses the actual checked-out PR/source SHA rather than GitHub's temporary merge SHA.

## Evidence available locally

Counts overlap and must not be added. These checks do not replace canonical frozen-source CI.

| Check | Observed result |
|---|---|
| Core combined feature/verification selection | 151 passed |
| B3/C0/production Android-runtime selection | 201 passed |
| JavaScript contracts | 30 passed, zero skipped/TODO |
| Critical notes/Focus Reading/Library/runtime browser selection | 26 passed |
| Current backup/media/native regression selection | 38 passed |
| Current build identity/package scan/upload/splash selection | 21 passed |
| Review | Independent review; material findings reproduced and repaired |
| Full local diagnostic Python/browser suite | 3,756 passed, 2 failed, 8 skipped (17m09s). The failures were the old light-splash/first-Activity and animator assertions loaded before the source evolved. Current splash/JVM tests passed separately. Four skips were unavailable private originals and four were the initially missing javac executable; current JVM checks run via the installed compiler module. This run is not frozen-source release evidence. |
| Canonical Linux/Windows and installed Android | Pending integration PR |

## Release process and limitations

The normal integration PR must pass exact-source canonical and installed checks before merging. The merge title `Release ANVAYA unified Android 1.2.0` intentionally triggers the new GitHub release workflow only after successful canonical main verification. It rechecks current main, builds app/test APKs once from that merged SHA, tests that same binary on API31/API35, verifies package/signature/provenance and publishes a versioned debug prerelease. It downloads and compares the public release asset byte for byte. No production signing credential is invented.

The APK is self-contained for its supported offline academic operations: Python and its server run on the phone. Cloud AI and Python internet access are disabled. Tutor is deterministic/source-based, not an on-device generative model. Physical phone behavior, specific third-party players and private academic-source certification remain unverified. Legacy PPT requires conversion for indexing; OCR may be unavailable. Full backups remain limited to 100 MiB; records-only export explicitly excludes note attachments. A debug-signature mismatch can prevent updating an older test APK: preserve/export data before any uninstall or storage reset.

No user data was migrated, reset, read from an installed phone or discarded. Source branches remain intact. The resolved-candidate manifest retains the original automatic-merge conflict diagnostic and independently requires ancestry from current main and every live source head; it remains explicitly unverified. Its tests passed 64 cases. No final APK URL is claimed in this candidate report.

## Final integration corrections before the last frozen candidate

- The Android build/JVM stage passed. The first installed jobs stopped before launch because setup-android v3 requested the removed `tools` SDK package. Explicit supported package inputs preserve both API31/API35 gates.
- A new picker-test IntentFilter intercepted null-action app launches. Launcher screenshots and logcat proved MainActivity was never started. Its exact-action monitor and real touch input fixed the test without weakening the upload assertions.
- Diagnostic source `be917bb07117ca7e2a6f193520a29461b45b8ffe` passed 13 installed cases on each of API31 and API35, including original PDF upload, offline academics, restart/update, external read grants, nested notes and startup. This is diagnostic evidence, not final-main certification.
- The existing `NativePdfPageTest` was compiled but omitted from the common installed script. It is now mandatory as an additional case, verifying page 2 of an original three-page PDF through the private URI.
- Windows still reported transient access/sharing errors after owned readers were synchronized. Only WinError5/32/33 now receive bounded retries (six atomic-replacement attempts, at most 620ms delay) of the identical completed snapshot. Permanent failure preserves old records and removes staged media. Four RED-to-GREEN contracts cover transient and permanent failures. A separate Windows probe passed the notes/backup/nested group and twenty independent runs of the original concurrent-tap case; none may fail.
- No test was disabled, no failing assertion was softened, and no production or private-data authority was granted. Diagnostic branches remain separate from the integration source. Final canonical and installed gates must run on the consolidated source and again on merged main before publication.

- The new native PDF diagnostic passed on both API31/API35 using the existing authenticated signed APK pair (`40264692706`). The consolidated installed script now runs all six test classes / fourteen cases on each API, rather than merely compiling the renderer.
- Canonical Linux identified an obsolete concurrency-test rendezvous behind the new shared read lock and an immediate theme attribute read before deferred JavaScript completed. The rendezvous now occurs at the request boundary while preserving the no-overwrite/stale-version checks; the theme uses the same exact expected value with Playwright’s normal retry. The changed companion module plus the formerly failing browser case passed 17 tests locally.

## Subsequent exact-source gate diagnostics

- Candidate `17b83b67a489e943f988166ad5a8f5db81583b59` passed canonical Linux, all focused feature workflows, Android build/JVM and all fourteen installed API35 cases. API31 stopped before a picker selection, so this candidate was not merged or released.
- The Windows full suite reached approximately 89% with no assertion failures before its 2,100-second process deadline expired. Its remaining focused categories passed, but an incomplete run is a failure. The process now has a bounded 4,200-second budget and the job 90 minutes; no cases, assertions or skip rules are removed.
- Diagnostic branch `ci/unified-picker-focus-probe-2026-10-26` captures the upload screen before Activity teardown. Its API31 failure recorded `dialog=false`, zero picker calls, a focused app and no UI error: the test clicked the parsed form before the deferred Library script attached its handler. The test now waits for the new Library page's complete load before clicking, waits for a focused rendered window, requires exactly one real picker intent and verifies the stored document count increases. This is test synchronization, not a replacement for the production immutable-upload repair. Exact-source reruns remain required.
- Current local validator deadline contracts passed 12 cases; JVM upload snapshot checks passed 2 with the installed compiler module; verification V2/coordinator checks passed 64. These counts overlap earlier selections and do not certify Android or Windows acceptance.
