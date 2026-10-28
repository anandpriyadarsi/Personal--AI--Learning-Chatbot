# ANVAYA Notes and original PDF delivery — 1.3.0 candidate

## Scope and source

Development starts from unified main `6c1c1fb97640172dc3bd86090e4ef113c94a9c12`. The relevant older Notes, Focus Reading, Library and Android branches are already retained in main; their open draft PRs are not blindly merged again. Application ID, data roots, original opening artwork and `Personal Learning Intelligence...` remain unchanged.

## Implemented behavior

- Compact dark/turquoise Notes cards; pinned group, persistent grid/list views, title/content search, and optional course/type/pinned/archive/trash filters.
- Six creation flows in the floating menu: text, handwritten pages, checklist, image, audio and document. Captures reuse existing Notes and media storage.
- Reading-first note content and independent nested sections. Overflow contains editing, rename, pin, course, sections, attachments, Focus Reading, archive and confirmed Trash actions. New lifecycle metadata is additive; Trash retains content and supports restoration.
- Focus Reading expands full content and hides editing, section management, upload controls, overflow menus and unrelated chrome; existing media remains readable at the bottom.
- Android PDF taps open the original managed blob through ACTION_VIEW/application/pdf and a read-only content URI, respecting system defaults. Open with uses a chooser; share and export are separate. Explicit internal matched-page reading remains available.
- Original bytes, stable IDs, hash, type, size and current display filename are preserved. The provider exposes only original blobs; it rejects write/delete attempts and unrelated paths. Import copies provider streams into existing managed storage. New content indexing is opt-in; viewing performs no extraction or AI operation.

## Verification record

This source report records observations made during implementation. The exact final commit and actual APK provenance are in the PR checks, installed logs and release `BUILD.json`; this document alone does not certify a release. Overlapping selections must not be added together.

| Check | Observed result / release gate |
|---|---|
| Existing JavaScript contracts | 30 passed, zero skipped/TODO |
| Package payload/version/signature scan contracts | 15 passed |
| Notes core lifecycle and existing backend contracts | 96 passed (final combined backend/compatibility selection) |
| Existing Notes separation/inline/visual-library contracts | 42 passed |
| Original Library storage/routes/JVM and browser selection | 42 passed |
| Notes and existing nested/media real Chromium journeys | 29 passed; final 21-case Keep selection after layout adjustment passed |
| Final combined Notes/Library/Android/browser selection | 190 passed in 70.29s, zero failures/skips |
| Complete local Python/browser suite | Running at candidate preparation; inspect final PR report |
| Canonical final-source Ubuntu and Windows suite | Required PR and main gates |
| Local native app + instrumentation source compilation / JVM unit tests | Passed; 9 JVM cases, zero failures; installed execution still required |
| Build-once signed APK and API31/API35 installed checks | Required before publication |
| Samsung Galaxy M11 / actual OneDrive, Acrobat or Google Drive apps | Not tested in this environment |
| Cloud provider selection | Synthetic changing-provider picker tests; actual OneDrive provider not tested |
| Restart | Activity recreation and separate process force-stop/reopen installed cases; physical phone reboot not tested |

The five new installed PDF tests inspect the production intent, read the URI from a separate UID, render its first original page through Android PdfRenderer and assert a three-page count, check the current filename, compare original hashes, reject writes/deletes, test chooser cancellation/no-viewer behavior, and reopen after Activity and process restarts. Unicode filenames are covered by host-side storage/export tests. The test receiver is a real installed synthetic PDF viewer, not a claim that specific vendor applications were tested. Scanned/mathematical/diagram/multipage originals and storage limits are covered by synthetic files; large-file performance on the M11 is unverified.

Requested screenshots are captured by real Chromium and by installed Android acceptance. The release publisher requires the Android Notes main/creation/reader/overflow screenshots and external PDF viewer/error/restart screenshots before it can upload assets.

## Signing and installation

Production signing credentials and the prior runner's debug private key are unavailable. This candidate uses debug signing and must remain a **prerelease**. The publisher verifies the APK signature and records its certificate and whether it matches the published 1.2.1 certificate in `BUILD.json`. A higher version code (18) and the same application ID permit updates only when the certificate also matches. Same-key replacement tests do not prove compatibility with a differently signed old installation.

On the Samsung Galaxy M11:

1. In the existing ANVAYA app, open Settings → Manage courses & backups → Export private backup. Keep the unencrypted ZIP in a location you control. Full backup is limited to 100 MiB; independently export original documents and note media if the workspace exceeds that limit. A records-only backup does not include all media.
2. Download the new APK from the versioned release. Allow installation from the browser/Files app when Android requests it, then attempt the update.
3. If Android reports a signature conflict, stop and retain the old app. Do not clear storage or uninstall to bypass the conflict. Update-in-place needs the old signing key. A replacement installation is safe only after a verified full backup plus independent copies of all excluded originals/media are available.
4. Restore with Manage courses & backups → Verify and stage restore, then close/reopen ANVAYA. Check Notes, attachments, original documents and assessments before discarding backup copies. If the backup cannot be verified, retain the old installation.

No user records were reset or migrated during development. This environment has no access to the owner's installed app data. Normal local Notes and stored-PDF operations use the embedded phone runtime; online generative AI is not included or claimed. The existing cloud-AI-disabled build behavior remains.

## Completion boundary

A successful release workflow proves the exact built APK passed its declared emulator gates and that the public download matches its hash. It does not establish production signing, update compatibility with a different certificate, physical M11 performance, actual phone reboot persistence, private academic-source certification, or specific cloud/viewer application compatibility. Failed or unavailable checks must be reported explicitly; a previous APK is not a substitute for this candidate.
