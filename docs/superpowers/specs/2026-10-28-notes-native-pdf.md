# Notes and original PDF delivery

The owner's detailed implementation request is the authority for this change. Work proceeds on an isolated development branch from main `6c1c1fb97640172dc3bd86090e4ef113c94a9c12`; no additional design approval is needed.

## Product behavior

My Notes becomes a compact dark/turquoise card library with search, persistent grid/list selection, pinned notes first, optional course/type/pinned filters, and a floating creation menu. The menu offers Text, Handwritten, Checklist, Image, Audio, and Import Document flows through existing notes storage. An opened note prioritizes its title, formatted content, nested sections and existing media. Editing, naming, pinning, course mapping, sections, attachments, Focus Reading, archive and confirmed deletion move to the overflow menu. Nested section independent saves, search, ordering and expansion persist. Focus Reading exposes content and existing media with an exit control and no authoring interfaces.

Library file taps open original PDFs using Android ACTION_VIEW with application/pdf, safe read-only content URIs, and system defaults. Open with explicitly uses Android's chooser. Original pages and bytes remain untouched; viewing never opens Tutor or invokes AI/indexing. Missing viewers/files and invalid files produce clear errors. Import copies provider bytes into existing durable managed storage, independent of expiring provider URIs. Rename, course mapping, share/export and confirmed deletion remain available. Search indexing stays an explicit separate operation. The existing native matched-page reader remains an explicit reading option.

## Architecture and alternatives

Use the existing Flask/embedded Python/WebView application, JSON Notes repository, nested/media services and content-addressed Library. Extend native Java request parsing and FileProvider integration. Replacing this with a new Android UI or a second document store would duplicate persistence and expand migration risk, so those approaches are excluded. Browser navigation alone cannot satisfy installed-viewer requirements.

## Constraints

- Preserve application ID `in.anvaya.privateapp`, data roots, existing records and backup contracts.
- Preserve static approved opening artwork and exact tagline `Personal Learning Intelligence...`; no splash animation.
- Android 12 is the primary target; minimum SDK remains 24 and target SDK 35.
- Do not change unrelated academic modules or merge incomplete drafts. Main already retains the relevant integrated draft work.
- No claim of offline generative AI, specific third-party app compatibility, physical Samsung testing or production signing without evidence.
- Publish only a built, signed and actually tested APK. Existing releases use disposable debug signing; do not imply safe update compatibility without matching certificates.

## Verification and delivery

Run failing then passing tests for behavioral changes, real narrow-screen browser journeys and screenshots, existing regression suites, native/JVM contracts, and installed Android tests where available. Review source and CI for the precise final commit before merge. Build the final merged source through the existing build-once Android workflow and verify release assets. If tooling, signing, permissions or tests block release, preserve completed source and evidence and identify the exact blocker.
