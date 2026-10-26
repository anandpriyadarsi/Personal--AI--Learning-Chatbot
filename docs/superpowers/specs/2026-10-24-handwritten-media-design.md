# Handwritten notes media
The owner's supplied nine-objective specification authorizes implementation and delivery without a further design checkpoint.

Build on Android performance PR #44 (`fddda918`), which contains current main (`e94b302`), rather than copying the older APK branch. Leave unrelated PRs intact. Preserve PDF/image notes, assessment records and existing navigation/privacy protections.

Keep media metadata in a separate `media` list on the existing note, with files in its app-managed `media` subdirectory. Add a lazy list and Attach Media on saved handwritten note readers, plus Rename, Share/Export and Delete. Stream uploads and downloads; validate container headers, size and SHA-256 without transcoding. Support the eight requested extensions and OGG only if added explicitly later. Limit one file to 512 MiB, one batch to 20, and one request to 1 GiB.

Android intercepts only same-origin, user-gesture, main-frame note-media open/share links. A native-only Python resolver validates IDs, ownership, integrity and canonical storage paths. FileProvider exposes only the notes-asset subtree; a read-only subclass forbids mutation and non-media paths. ACTION_VIEW gets a content URI, MIME and temporary read grant. Android defaults/chooser select the player. No JavaScript interface, private URLs, player controls or hardcoded player package.

Direct sharing of the existing private file avoids copying large videos into a cache or sending localhost authentication to another application. Browser links download instead. Storage is local, works offline, and adds no cloud service. Full codec validation/autoplay belong to the receiving player; header and integrity checks cannot certify a decodable media stream.

Verification: Python storage/routes and existing notes/runtime tests, real responsive Chromium journey, JVM URL-policy tests and installed emulator ContentProvider/intent lifecycle instrumentation. No real-device or MX Player claim without actual evidence. Prepare a feature PR; do not merge before applicable dependency/regression checks pass.
