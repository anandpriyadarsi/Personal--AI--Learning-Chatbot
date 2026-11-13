# Phase 1 completion pass

Continue approved A/B design on current main, including PR #77. Preserve existing dirty files in the original checkout by using a new worktree.

1. Test-first: restore exact selection from status; give new manifests a valid first-cue URL, including transcripts beginning after zero.
2. Complete reader UI: bounded crop controls and overlay, invalidate reviews after edits, multiple named supplied frames (up to 20), resume queued polling on reload, readable consent scope.
3. Add an offline validation command with platform/exit-code/skip reporting and no personal-store activation or provider keys. Make Chromium tests portable to Windows installations.
4. Run new and relevant existing tests and real browser journeys, review, then integrate if gates pass. Live model quality and actual Windows results cannot be certified by this Linux host. Optional C stays deferred per approved dependency gates.
