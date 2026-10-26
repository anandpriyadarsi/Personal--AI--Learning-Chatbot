# ANVAYA 1.2.1 opening and release plan

The owner's supplied 864 x 1536 image is the complete static first app-controlled opening. Preserve its exact original JPEG bytes (despite the uploaded .png name), blue logo, black background and tagline ending three literal dots. Use a density-independent drawable with proportional FIT_CENTER on black, no additional title or animation. Hide system bars only during this opening and restore them for the existing workspace. Android 12+ uses a black system splash placeholder instead of the old mark. Existing delayed/error recovery remains accessible above the image.

## Implementation tasks

- [ ] Replace the first app-controlled view with the supplied image. Verify portrait/landscape rendering, full source visibility, static behavior, accessible description and error actions through real Android Views; preserve first-paint transition and Activity lifecycle guards.
- [ ] Bump the debug prerelease to 1.2.1 / code17. Retain canonical Ubuntu/Windows verification, shared API31/API35 installed acceptance and same-binary publication. Include source-image identity and emulator-rendered opening evidence in release assets.
- [ ] Inspect each remaining live PR head against main and the integration matrix; incorporate only new compatible work if any. Preserve superseded originals and user data.
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
