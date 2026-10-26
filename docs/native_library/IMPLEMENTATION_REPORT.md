# Original document Library — implementation and verification

Started 24 October 2026; verification continued 25 October 2026.
Main baseline: `e94b302ddd6d1013a30415662b431fe1f521f3f7`.
Separate Android baseline: draft PR #44, `fddda91` (includes #43/#42).
No main merge or installed production migration performed.

## What works in the shared web application

Open **Library → Files — upload and manage original documents** (`/library/files`).
The legacy registered-source, content-search and saved-link views stay accessible;
existing canonical source IDs, documents and academic relationships are untouched.

- Stream/store original PDF/PPTX/PPT, 100 MiB/file, original name and SHA-256.
  No original conversion, notes, summaries, quizzes, lessons, external AI or cloud.
- Display rename, download original, browser file sharing where supported, explicit
  copy, confirmed delete, details/storage location, subjects/topics/tags, folders
  and subfolders with cycle prevention, breadcrumbs, sort/filter, list/grid.
- Private persistent page/slide text index, exact normalized phrases, casefolding,
  punctuation/whitespace normalization, snippets and ranked paginated results.
  Folder search includes descendants; folder browsing lists direct children.
- PDF page text via pypdf; PPTX slide text follows presentation relationship order
  rather than lexicographic archive filenames. Multiple positions/file appear.
- Stored/Indexing/Ready/Partial/OCR Required/Conversion Required/Failed/Disabled
  are explicit. One background worker, generation-checked publication, per-page
  cancellation checks, persistent queue recovery, retry and rebuild.
- Optional local English OCR requires Tesseract and PyMuPDF; it never changes a
  PDF. Mixed PDFs disclose unsearchable pages. OCR is not assumed on Android.
- Open at Match: original PDF page preview on desktop with page navigation,
  zoom/fullscreen and highlighting where the renderer finds the literal text;
  optional browser original-PDF iframe. PPT/PPTX preserve originals and provide
  an external-viewer/download fallback with the required slide number visible.
- Explicit Learning Studio handoff enters the existing authored JSON/ZIP import
  workflow. It does not create a raw-file conversion engine. Existing Studio
  still requires a separately registered PDF source and reviewed authored package.

## Architecture and changed components

| Component | Files | Decision |
| --- | --- | --- |
| Storage and jobs | services/native_document_library.py | Additive private sidecar, immutable hash-addressed blobs, stable document/folder IDs |
| Extraction | services/native_document_extraction.py | Local bounded pypdf/OOXML; optional OCR; original untouched |
| Routes | ui/web/native_library.py and create_app registration | Same-origin tokens, explicit actions, no-store private responses |
| UI | native_library.html, native_document.html, native_learning_handoff.html, native_library CSS/JS | Mobile file manager, existing workspaces preserved |
| Tests | test_native_document_library.py, test_native_library_routes.py, test_native_library_browser.py | Integrity, phrase positions, races, recovery and actual browser journeys |

Paths above are relative to `personal_learning_assistant/`, except tests in `tests/`.

### Database and migration

`data/native_library/library.sqlite3`, schema `user_version=1`. New `documents`,
`folders`, `pages`, and `page_fts`; no canonical database migration. The metadata
DB is **not** disposable: only pages/FTS may be rebuilt. FTS5 is preferred; where
SQLite omits FTS5, bounded exact normalized SQLite page search keeps originals
and content search functional, with lower scalability. Future schema versions
are refused rather than silently downgraded.

Atomic streamed temp writes + fsync + rename; blob paths never derive from user
filenames. Metadata commits follow blob storage. A crash can leave an orphan blob,
not a live reference to an intentionally deleted file. Explicit copies share the
blob; last-reference deletion cleans it up. Original reads verify length and SHA.
Folders and subject IDs are separate. Rename/move/remap join live metadata to the
same page index. No destructive original/academic migration exists.

### Privacy

Content indexing is local and enabled by default for new uploads; users can opt
out during upload or disable per file. Disabling removes page text/FTS rows and
cancels publication of pending work; name/topic/tag search still works. SQLite
`secure_delete` is enabled, but this is **logical index removal, not a forensic
secure-erasure guarantee** for SQLite FTS segments, OS snapshots or older backups.
The store is app/host private, not encrypted at rest by this feature. No provider
calls, tracking endpoints or paid infrastructure are added.

## Verification already executed

Commands run from the shared worktree:

```sh
python -m pytest -q tests/test_learning_library_routes.py tests/test_learning_library_read_model.py
# 75 passed baseline
python -m pytest -q tests/test_learning_library_routes.py tests/test_learning_library_read_model.py tests/test_native_document_library.py tests/test_native_library_routes.py
# 97 passed at the first shared implementation commit
ANVAYA_BROWSER_TESTS=1 python -m pytest -q tests/test_native_document_library.py tests/test_native_library_routes.py tests/test_native_library_browser.py
# 27 passed including real 360/390/1366 Chromium journeys
python -m pytest -q
# 3013 passed, 280 skipped, 0 failed (391.10 s); skips are not passes
node --check personal_learning_assistant/ui/web/static/js/native_library.js
# passed
```

The initial complete run did not enable opt-in browser tests; the new browser
journeys ran separately. Subsequent theme/mobile refinements were retested with
real Chromium. Screenshots were visually inspected and a narrow-screen header
collapse was fixed with a height assertion. Dark and genuine saved-light-theme
journeys test upload, async status, original download byte equality, search,
page-2 opening, within-file search, fullscreen, rename, tags, folders/move/delete.
Tests also cover local real OCR, mixed/empty/invalid documents, FTS5 absence,
copy/reference deletion, interrupted upload cleanup, job restart, deleted/disabled
late worker publication, corrupt-index rebuild, ranking pagination and nonblocking
browse/download while the indexer is busy.

## Measured synthetic desktop performance

One local run, no phone speed claim:

| Original | Size | Positions | Store | Index | First 50 search hits |
| --- | ---: | ---: | ---: | ---: | ---: |
| PDF | 215,999 B | 500 pages | 0.0411 s | 0.6501 s | 0.0027 s |
| PPTX with 12 MiB synthetic media | 12,717,799 B | 500 slides | 0.0740 s | 0.0695 s | 0.0019 s |

Original bytes and all 500 indexed positions were checked. These fixtures exercise
long documents and large presentation media; they are not a representative
low-memory Android benchmark. No thumbnails or full-document rendering runs on
initial Library load. Metadata is paginated (30 rows), polling is visible-page
bounded, and previews are loaded only for the selected page.

## Android integration and release boundary

The separate Android candidate adds an explicit phone-private root, safe
FileProvider original copies/read grants, MIME-aware external PowerPoint opening,
sharing and an internal bounded Android PdfRenderer page viewer. Native PDF
page requests can select the requested page; native support remains **unverified
until installed instrumentation passes**. A browser find fallback returns to the
same private index. Existing SAF import and save picker are preserved.

Native backup includes new originals and sidecar, excludes upload temp files,
serializes Library storage with export and verifies referenced blob hashes before
staging restore. Existing pre-restore rollback copies remain unchanged.

Host Android tests: 22 passed, 1 skipped (JDK compiler unavailable). This includes
production isolated phone-runtime, backup, navigation/performance and new native
backup contracts. Java, instrumentation, actual Files provider imports, intent
chooser, pinch gestures, rotation and same-key APK update acceptance have not
run locally. The machine has a Java runtime but no javac, Android SDK, adb or
emulator. Gradle distribution download fails with `java.net.SocketException:
Network is unreachable`. **No local APK was built or certified.** API31 and API35
hosted build/emulator gates are prepared; their eventual status must be checked,
not inferred from this report.

## Remaining limitations

- Legacy PPT needs a separately converted PPTX copy for search; original stays usable.
- Image-only PPTX text is not OCR indexed. PDF OCR is optional English-only and
  limited to 100 pages; text extraction is capped at 2,500 positions / 12M characters.
- External PowerPoint slide deep links are not claimed. Native PDF selection needs
  device verification. Desktop PDF highlights use literal renderer matching, so
  a normalized punctuation match may show context without a highlight.
- Registered legacy sources remain in their existing views. This does not silently
  copy, migrate or reindex every historical source into the new file store.
- Authored Learning Studio packages/source registration are still required; the
  handoff is explicit and does not fabricate academic source identities.
- Original hash verification and streaming storage remain request work. Heavy
  extraction/OCR is background; upload cancellation cannot undo a request whose
  complete original was already committed. Temporary/orphan files from process
  death are not automatically garbage-collected, to avoid deleting recoverable data.
- Existing Android backup retains its 100 MiB total archive/expanded-data limit;
  a growing Library can exceed it. Individual originals can still be downloaded.
- No real physical Android 12/newer-device performance or install certificate.

Keep both work streams draft and unmerged until platform/repository gates pass.
