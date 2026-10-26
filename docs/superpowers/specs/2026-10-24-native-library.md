# Native original document Library

Authority: owner supplied 11-objective implementation request, 24 October 2026.
Original PDF/PPT/PPTX bytes are canonical. No automatic Notes, Learning Studio,
AI or academic registry writes. Existing read-only registered Library remains
accessible; a Files tab provides the new manager without remapping legacy IDs.

Use a private additive SQLite database under the installed data directory and
content-addressed blobs, independent from academic ownership and Studio storage.
Atomic streamed uploads (100 MiB bound), SHA-256, stable document IDs, reference
counted copies, folder IDs separate from course IDs. A bounded background worker
indexes pages/slides in SQLite FTS5. Default search is a normalized exact phrase;
no fabricated synonym matches. Queue survives process restart; generation checks
prevent deleted/disabled indexes returning after worker completion.

PDF text uses pypdf (also packaged on Android). Optional OCR requires local
Tesseract plus PyMuPDF and explicit per-file consent. PPTX uses bounded OOXML
reading in presentation order. Legacy PPT remains original/downloadable with an
explicit conversion requirement. Embedded PDF viewer uses native PDF on browsers,
optional server rendered pages on desktop; Android PdfRenderer/external viewers
are an integration concern. Never claim external slide deep linking.

Reuse Flask/Jinja, same-origin action tokens, local static JS/CSS, private no-store
responses. All uploaded names are untrusted metadata, never storage paths.
The Learning Studio action must describe the existing authored-package workflow;
raw automatic PDF/PPT conversion is not supported by that workflow.

Android runtime exists only on draft branch #44 (stacked #43/#42). Main baseline
is e94b302. Shared implementation first, then test integration on latest Android
branch without merging draft Android code into main. No SDK/adb is currently
available; attempt infrastructure discovery/build and report exact blockers.
