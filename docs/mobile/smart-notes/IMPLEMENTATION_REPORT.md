# Smart Notes, Obsidian and Android startup

Implementation date: 25 October 2026. Delivery: [draft PR #55](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/55). This branch is not merged into main.

## What changed

| Area | Implemented behavior |
| --- | --- |
| Nested notes | A main note contains independently editable Markdown sections. Compact cards start collapsed; one section opens by default. Users can add, rename through Edit, reorder, duplicate, delete with confirmation, move supported sections, expand/collapse all and search section bodies. |
| Legacy notes | Existing IDs, body, academic metadata and original pages remain. The existing typed body is presented as Original Content without splitting paragraphs. No database migration or reset. |
| Safe copies and moves | Copies receive independent media and inline-image identities. Moving a section transfers its media; failed writes roll back destination files. Deleting a section keeps its attachments on the main note. Sections containing legacy inline-image references cannot be moved between notes; copy/upload the referenced images first. |
| Attachments | Typed and handwritten notes share the existing streamed attachment store. Attach at main-note or mini-note scope; rename, open, download/share and remove without changing note text/pages. New notes must be saved before audio/video/document attachments are added. |
| Android file opening | Native ACTION_VIEW/ACTION_SEND use content URIs, exact supported MIME types, ClipData and temporary read grants. Android chooses the installed application. No embedded audio/video player. A missing viewer offers share/save. |
| Mobile PDF pages | Legacy handwritten PDF pages retain an explicit Open PDF link. Mobile never automatically loads a PDF iframe, because WebView otherwise launches Android's Save picker while opening the note. Desktop previews remain lazy. |
| Obsidian | Library → Connected Sources → Obsidian. Existing desktop vault reader, search, links/backlinks and sanitized rendering are retained. Android imports a clearly labelled Markdown ZIP snapshot; users can copy selected notes into independent ANVAYA notes and disconnect without deleting source material. |
| Startup | Existing ANVAYA logo on #F8FAFB; logo pop/fade, brand name and Personal Learning Intelligence. Reduced-motion users see static branding. Runtime starts concurrently; the native cover is removed after the first committed WebView frame, without waiting for animation completion. Slow/error recovery is explicit. |
| Web/PWA | Light manifest launch background; normal application dark styling is preserved. Compact note headers/cards, search control and bottom navigation remain. |

## Storage, scope and limits

- Note sections are additive JSON fields in the existing independent notes store. Stable note identifiers and existing assets remain valid. Optimistic versions and the existing shared write lock prevent silent stale overwrites.
- Up to 200 explicit sections per main note and 500,000 characters per section. Section bodies render only when opened; metadata/search requests do not fetch media bytes.
- Supported attachments: MP3, WAV, M4A, AAC, MP4, MKV, MOV, WebM, PNG, JPG/JPEG, PDF, TXT, MD, CSV, DOCX, PPTX and XLSX. Container signatures are checked; external apps determine codec/document compatibility. Legacy Office .doc/.ppt/.xls and executable/web formats are not accepted by this attachment flow.
- Media limit remains 512 MiB per file, 20 files and 1 GiB per upload, subject to available storage. Whole-workspace Android backup retains its existing 100 MiB / 1,000-file bounds; large media collections can exceed backup capacity.
- Android's existing file picker chooses a vault ZIP. Direct shared-folder SAF access and live synchronization are not implemented or advertised. Snapshot limits: 25 MiB compressed, 100 MiB expanded, 2,000 entries, 500 KB per Markdown note; up to 20 selected notes copied atomically. Attachments and Obsidian settings are excluded. Previous snapshot files are retained on replacement/disconnect.
- Snapshot identity rebases safely after backup restoration to another runtime root. Ordinary ANVAYA notes never depend on the vault connection.
- Android app links open only validated, gestured `obsidian://open` links with known vault/note destinations. Snapshot mode suppresses misleading original-vault links. Opening Obsidian is not synchronization.

## Parallel-development composition

Baseline: PR #47, `ab73e63c796d59bbf1f57d8956f2c04226f97ca9`, including PR #44's native navigation optimization. No other branch was reset, merged or overwritten. Separate Library/performance/Assessment changes remain separate and need deliberate integration.

The shared coordinator script/tests are reused from PR #53. Run focused feedback locally; full cross-platform/native gates remain required. This branch does not replace the independent CI workflows with draft-skipping rules from the separate coordinator development.

The original published implementation `b0d1190b9b523c6a78607b5ff29f37393c8035a0` matched local tree `dcae6c3312a657ab5d390b2f92548f7f9f096114` exactly. Later fixes address raw ZIP names on Windows and the installed Android PDF-picker defect; use the latest PR head for current verification.

## Verification evidence and current boundary

The live PR checks and exact-head Actions artifacts are authoritative. Never transfer a pass or APK certificate from an earlier head to a later head.

- Service/routes cover legacy preservation, independent edits, stale versions, malformed requests, section search/order, cross-note media move/rollback, concurrent section deletion during upload, independently removable duplicate media/inline images, and restart/read behavior.
- Actual Chromium journeys at 360/390/430 CSS pixels cover collapsed sections, one-open reading, edits, search, attachments, reload and overflow. Existing handwritten media journeys cover 360/390/1366. Screenshots below are running synthetic application captures, not mockups.
- The first GitHub APK/JVM job passed. Its API31 emulator run reproduced an automatic PDF Save picker; the mobile preview regression was fixed rather than relaxing the gesture test.
- Windows found ZIP filename normalization. A Windows-separator simulation first failed, then passed after checking the original raw ZIP names. The malformed archive fixture preserves raw filenames across operating systems.
- The shared coordinator produced FAST_PASS_ONLY, which is development feedback, not merge or release authorization.
- The resumed local environment lacked a complete Chromium ICU runtime and Java compiler/SDK. Local browser rerun errors are environment failures, not browser passes. GitHub installs its own complete browser/runtime and runs the native build, JVM and emulator checks.
- Physical phone, real MX Player/VLC decoding and existing-phone signing/update compatibility have not been certified. No physical-device claim is made.

## Reproduce

Use the branch's tracked requirements in a clean Python 3.12 environment:

```bash
python -m pip install -r requirements-mobile.txt
python -m playwright install --with-deps chromium
python -m pytest -q tests/test_nested_notes.py tests/test_nested_notes_routes.py tests/test_obsidian_connections.py tests/test_notes_media.py tests/test_smart_splash_contract.py
ANVAYA_BROWSER_TESTS=1 python -m pytest -q tests/test_nested_notes_browser.py tests/test_notes_media_browser.py
node --test tests/js/*.test.cjs
python scripts/verification_coordinator.py --base ab73e63c796d59bbf1f57d8956f2c04226f97ca9 --head HEAD --execute --json shared-verification.json
ANVAYA_BROWSER_TESTS=1 python -m pytest -q
```

On PowerShell, set `$env:ANVAYA_BROWSER_TESTS='1'` before the browser/full commands.

For native builds, use JDK 17, Android SDK 35 and Gradle 8.11.1:

```bash
python scripts/android_acceptance_fixture.py android/app/src/androidTest/assets/acceptance
gradle -p android assembleDebug testDebugUnitTest assembleDebugAndroidTest
bash scripts/android_emulator_acceptance.sh
```

The installed acceptance script uses an already running API31 emulator. It installs the synthetic fixture APK and test package; run it only on a disposable emulator. Package: `in.anvaya.privateapp`, version code 15 / `1.1.4-notes-test`. A successful build alone does not certify installed behavior.

## Screenshots

- [Nested notes, 390px](screenshots/nested-notes-390.png)
- [Expanded section and attachments, 390px](screenshots/section-attachments-390.png)
- [Obsidian connection, 390px](screenshots/obsidian-settings-390.png)
- [Obsidian browser, 390px](screenshots/obsidian-browser-390.png)

Native screenshots, when produced by installed instrumentation, are in the exact-head emulator artifact. A native splash screenshot is not claimed unless that file actually exists.
