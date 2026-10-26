# ANVAYA 1.2.1 opening and release plan

The owner's supplied 864 x 1536 image is the complete static first app-controlled opening. Preserve its exact original JPEG bytes (despite the uploaded .png name), blue logo, black background and tagline ending three literal dots. Use a density-independent drawable with proportional FIT_CENTER on black, no additional title or animation. Hide system bars only during this opening and restore them for the existing workspace. Android 12+ uses a black system splash placeholder instead of the old mark. Existing delayed/error recovery remains accessible above the image.

## Implementation tasks

- [x] Replace the first app-controlled view with the supplied image. Verify portrait/landscape rendering, full source visibility, static behavior, accessible description and error actions through real Android Views; preserve first-paint transition and Activity lifecycle guards.
- [x] Bump the debug prerelease to 1.2.1 / code17. Retain canonical Ubuntu/Windows verification, shared API31/API35 installed acceptance and same-binary publication. Include source-image identity and emulator-rendered opening evidence in release assets.
- [x] Inspect each remaining live PR head against main and the integration matrix; incorporate only new compatible work if any. Preserve superseded originals and user data.
- [ ] Open a reviewable release PR; require all exact-head checks and independent final review before merge. Merge with title `Release ANVAYA unified Android 1.2.1` and require fresh canonical main checks plus new main-pinned APK build and installed acceptance before publication.
- [ ] Independently download the release asset, compare SHA256, inspect package/signing/build metadata and opening evidence, and report exact main SHA and limitations.

## Review focus

- A wide/rotated display must show the complete portrait artwork with black letterboxing, never crop it.
- System font scaling must not resize the raster artwork; long error messages and recovery buttons remain scrollable.
- A warm launch must still show a static opening until first workspace paint, with no artificial delay.
- Older Android system splash must not display the replaced mark.
- Source, same tested APK, package version, checksum and release metadata must agree; existing debug signing limitations must remain explicit.

No database/schema changes, source-branch deletion, uninstall, data reset or production-signing claim is authorized or needed. No changes to the already integrated academic implementations are planned unless verification reproduces a defect.

## Pre-release evidence

Base main `9a5c276ae5b57a1e048ff5e1af1d819376e7774e` already has PR58 and its successfully published 1.2.0 release (run40291899499). All fourteen currently open PR heads match the integration matrix exactly: twelve are ancestors of main; PR27/29 are explicitly superseded. None needs remerging. `2026-10-26-live-pr-heads.json` records the observed heads.

The supplied file is JPEG despite its upload filename. It is copied unchanged as drawable-nodpi/anvaya_opening.jpg; SHA256 `319e31420b50e2e420de571d0906835ee4f9894dedbd26b88435d0ca57415fb6`. The new missing-artwork contract failed before copying; current artwork/JVM/package scanner selection passes 20 cases. Android rendering and full exact-source platform gates remain pending.

## Independent review correction

Review found that a pre-draw View raster must not be presented as an actual displayed launch screenshot. Retain the portrait/landscape Android raster checks and replace launch evidence with actual `adb exec-out screencap -p` bytes captured during a fresh cold launch. A tile-based complete-artwork comparison rejects blank system splash, cropping, stretching, overlaid bars and substituted artwork. An independent regression failed before the matcher was implemented. Native tests now require actual WindowInsets reporting hidden system bars during opening and visible bars after workspace reveal. No production delay or test-only production hook is added.

Installed acceptance is also extended to explicitly reach Obsidian, its Android snapshot settings and Planning offline; exercise read-only Focus Reading and return to authoring; and upload an actual synthetic PPTX through the native picker and find its slide token through the production document search. These assertions supplement the existing PDF upload, Library/learning/assessment and persistence cases.

## API31 regression diagnosis

Candidate08eb326 passed all fifteen installed API35 cases and real cold-launch capture on both APIs. API31 repeated a rapid-reopen failure in the diagnostic run40302652391: `cover=false, web=true, flags=0, saved=0, status=true, navigation=false, hiddenObserved=true`. The workspace had painted; the navigation bar retained its hidden visibility request despite restoring legacy flags. Explicitly show system bars through WindowInsetsController at workspace reveal on API30+, retaining legacy restoration for older supported Android. Keep both actual-insets assertions, the timeout and all cases unchanged. Diagnostic capture is retained for future failures.

## Corrected API31 diagnosis and verification environment

The initial navigation-regression interpretation was incomplete. The same missing navigation bar exists in the previously released API31 screenshots, and the emulator log explicitly records `qemu.hw.mainkeys=1`. This AVD declares physical navigation keys, so no software navigation-bar source exists in application windows; requesting it cannot make it visible. Retain strict hidden/visible WindowInsets assertions, configure an explicit Pixel2 phone profile for both release APIs, and fail the runner if `qemu.hw.mainkeys=1` forces hardware keys; Android may leave it empty for default software keys, while actual navigation visibility must still pass. Use one WindowInsetsControllerCompat hide/show path, restoring the earlier bar behaviour. No late diagnostic intervention is included in release acceptance.

## Android15 visual regression and correction

Manual inspection of actual candidate API35 frames found status icons overlapping the header and the native keyboard obscuring the Tutor composer, despite older DOM viewport checks passing. A new actual-WebView bounds assertion reproduced the status overlap in diagnostic run40310567929 (`y=0, inset=63`). On API35+, apply system-bar/cutout and actual IME insets to the workspace root only; keep the static opening unpadded and full-screen. Add a physical-coordinate check that the focused Tutor input and send button clear the keyboard. Smart Notes captures now wait for display/accessibility quiescence, matching the existing offline capture helper, so read-only Focus Reading screenshots represent the composed state rather than an older frame. Keep all existing cases, assertions, API coverage and timeouts.

Diagnostic40311353671 passed all15 installed API35 cases after the inset fix. Actual composed Home, Tutor keyboard and Focus Reading screenshots were manually inspected: system icons no longer overlap the header, the input/send button clear the keyboard, and reading controls are read-only. The final PR source still requires its own complete platform and API31/API35 gates before merge and fresh main publication.
