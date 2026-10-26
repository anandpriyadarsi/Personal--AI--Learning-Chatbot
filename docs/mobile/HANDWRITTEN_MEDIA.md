# Handwritten audio/video attachments

Open a saved handwritten note, select audio/video files, then choose **Attach Media**. Creating the handwritten note still uses the existing PDF/image form; its reader offers media attachment afterward. Each attached file has tap-to-open plus Attachment options: Rename, Share / Export, Download, Delete. Removing media preserves the note and original pages.

Eight formats: MP3, WAV, M4A, AAC, MP4, MKV, MOV, WebM. 512 MiB/file, 20 files/batch, 1 GiB/batch; available phone storage also applies. Files stay in private local storage, work offline, and are never transcoded or preloaded by the reader. Header validation detects containers; decoding, codec support and autoplay belong to the receiving player.

Android requests ACTION_VIEW on a readable content URI with the correct MIME and temporary read grant. Android's default or native chooser selects installed players. No package is forced, and no internal player exists. A native-only Python resolver and read-only ContentProvider validate ownership, IDs, paths and integrity. Only a same-origin main-frame user gesture enters the navigation bridge; there is no JavaScript interface accepting private paths or arbitrary URLs. Return/cancellation preserves the WebView. Missing-player fallback offers Share or Save.

Ordinary browsers download the file; open the saved file with a device application. A browser cannot promise to launch MX Player directly. This implementation adds local attachments only, not remote cloud storage.

Uploads stream/hash outside the notes write lock. The metadata commit shares the existing note-store lock and reads the latest fields, preserving concurrent edits. Duplicate content is suppressed; reattaching an intact original repairs a missing/corrupt duplicate under the same attachment ID. Failed batches roll back new files; failed JSON commits restore staged replacements/removals. Metadata is lazy-loaded on handwritten readers only, and media endpoints avoid Android's SQLite request lock.

## Backups
The existing full Android backup has a 100 MiB safety limit. Larger media collections must be exported from the individual attachment menus. Device Settings also offers **Back up study records without audio/video**, preserving handwritten pages, notes and academic records within the existing limit. Its explicitly named ZIP excludes media blobs and removes media links from the exported notes copy only; live notes/files remain unchanged. This avoids raising in-memory backup limits or silently omitting media from a full backup.

## Verification ledger
- Initial missing-feature suite: 19 failures observed before implementation.
- Storage/route supported formats, restart/reopen, bounded reads, hashing, multiple attachments, rename/delete, duplicate concurrency, ownership, CSRF, Range downloads, symlinks and rollback.
- Review added missing/corrupt reattachment, repair rollback, slow-stream concurrent rename and records-only large-media backup regressions; red cases reproduced and corrected.
- Browser journeys: 360/390/1366 px upload/reload/rename/download/delete, no internal audio/video elements, no attachment-byte preloading, no horizontal overflow; failed-upload selection retained for retry.
- Android instrumentation: actual separate-UID synthetic recipient receives/read-opens content URI; read-only provider blocks write/pages; actual touch-to-navigation handoff with missing handler fallback; cancellation and force-stop persistence.
- Local Java compiler and Android SDK/emulator are unavailable. GitHub Actions performs JVM/APK/emulator verification. Read the PR's latest evidence for exact-head completion; a successful APK compilation is not proof of physical MX Player playback.
- No real Android phone, MX Player or VLC playback was physically tested.

## Independent review
One independent review found no Critical issues. Important missing/corrupt duplicate recovery and backup availability findings were fixed. Upload lock contention was treated as a responsiveness issue and fixed; file selection now survives a failed upload. Native origin/gesture, URI/read grants and provider boundaries were independently inspected. Windows CI found that HTTP tests left streamed responses open; tests now close complete and partial download responses before deletion.
