# Multimodal Tutor Phase 1

Local web extension of the existing Library and Academic Tutor. Both capabilities are opt-in. No personal stores were available or activated during development.

## Implemented

- **A:** Choose one image, PDF page or PPTX slide; review exact local scope; run bounded local inspection, provide an explicit transcription/correction, or opt into structured cloud visual reading of one image/PDF-page crop. An unrendered PPTX slide requires an exported PNG/PDF for vision. Original bytes remain unchanged.
- **A:** Existing leased Library worker publishes versioned artifacts into existing canonical chunks/retrieval. Explicit selection works without a lexical match. Unknown critical symbols cause a deterministic clarification without a provider call. Review text is separate from original bytes and carries user-transcription provenance.
- **A:** Source-only conversations stay in the existing Tutor, with existing compact composer/history. Each new evidence link has an immutable snapshot saved with the exchange. Citations resolve the retained original and location or show unavailable; generation/revision changes require reselection. Old conversations have an honest legacy fallback.
- **B:** Upload bounded UTF-8 SRT/VTT, preserve exact milliseconds, choose a cue, bind explicitly supplied same-course image frames and timestamps, and open a supplied YouTube reference at the cue. No video is fetched. Ready overlapping frame readings can join the selected cue in Tutor; an unprocessed/missing frame cannot establish board content.
- Strict locators, source/recipe/artifact identity, publication receipts, placement/course scope, expiry/revocation, integer micro-dollar reservations and stable paid-dispatch IDs. Unknown outcomes are not automatically resent. All Tutor repair/retry calls use the same guard when multimodal text is involved, including conversation history.
- Explicit backup-first optional activation, no schema writes on GET/import, additive optional canonical migration 0020, Native schema remains version 2. Feature-off hides new evidence from retrieval without deleting originals, corrections or receipts.

## Deferred and unverified

- **C deferred:** Local video/audio decoding and ASR. No FFmpeg, PyTorch, model weights, arbitrary URL download or background closed-app processing.
- Live model math/diagram accuracy and billing reconciliation from actual token usage are unverified. The ledger conservatively charges the reserved upper bound when actual usage is unavailable. Fake-provider passes do not establish educational quality. No model is selected by default; verify the chosen image-capable model, account access, current rates and privacy terms before configuring paid operation.
- Actual Windows execution is unverified; instructions below are PowerShell syntax. Linux tests do not certify Windows. Process timeout and pixel/byte bounds work in the code on both platforms; POSIX additionally applies CPU/address-space/file-size limits. A Windows process sandbox/Job Object is not supplied.
- Source selection is one page/image per review, up to 10 bounded chunks per selected interval, not full-lecture vision. Automatic slide rendering, crop-drawing UI, automatic grading/mastery/planner writes, and bidirectional vault sync are excluded.
- The retrieval pilot uses supplied user transcriptions for image cases. It does not measure OCR/vision transcription or real answer correctness. The text-only comparison is a projection of the same corpus, not a claim of a complete paired model benchmark.

## Safe PowerShell setup and activation

Run in your existing repository. Stop ANVAYA and all writers first. Preserve your configured database/root; the paths below are conventional defaults, not a request to create a new empty owner. This command refuses missing owners.

```powershell
# Use the existing environment. Substitute venv for .venv if that is yours.
.\.venv\Scripts\python.exe -m pip install -r requirements-multimodal.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m scripts.multimodal_migrate --database .\data\learning_assistant.db --library-root .\data\native_library
# After inspecting the dry-run result, with ANVAYA still stopped:
.\.venv\Scripts\python.exe -m scripts.multimodal_migrate --database .\data\learning_assistant.db --library-root .\data\native_library --apply
$env:ANVAYA_MULTIMODAL_ENABLED = "true"
.\.venv\Scripts\python.exe phase7_web.py
```

Open http://127.0.0.1:5000. Launcher remains loopback-only. Original Library initialization must already have been completed with your existing local app; do not create replacement empty databases to get past activation errors.

From Library, open an image/PDF and expand **Ask about this page/image**. Choose **Local inspection** (digital text) or **My transcription / correction**. Review the scope, approve processing, wait for Ready and use **Ask Tutor**. Ambiguous scans/images stay unknown until a transcription or separately approved visual reading exists. A failed question retains its composer draft.

For lectures, upload an authorized SRT/VTT (1 MiB / 2,000 cues / times below 24 h), open the transcript and choose a cue. To use frames, upload and explicitly process their readings first, then link each frame's displayed name and supplied timestamp. Use **Add another frame** to link up to 20 named frames in one manifest. Use distinct stored frame placements for distinct timestamps; explicit copies may share original bytes. A changed frame invalidates its manifest rather than silently following a new version. Citation cue text is highlighted with exact supplied bounds.

## Optional paid vision and answering

All limits default to zero/unconfigured. The implementation/tests authorize no spending. Configure keys privately through your existing local environment; never put them in Git, screenshots or command history. Only the selected normalized/cropped image is sent for visual extraction. Cloud answering sends selected derived text and relevant conversation history under a separate review/receipt.

| Local environment name | Meaning |
|---|---|
| `ANVAYA_MM_VISION_MODEL` | Verified image-capable model supporting Chat Completions and JSON output; no default |
| `ANVAYA_MM_VISION_KEY` | Private API key for the fixed official OpenAI endpoint |
| `ANVAYA_MM_VISION_MAX_MICROS` | Conservative maximum micro-USD per bounded image call; no default allowance |
| `ANVAYA_MM_ANSWER_MAX_MICROS` | Conservative maximum micro-USD per bounded entire Tutor request/repair; no default allowance |
| `ANVAYA_MM_MONTHLY_MICROS` | Shared monthly reservation ceiling for extraction and answering; defaults to 0 |
| Existing `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL` | Locally trusted HTTPS Tutor provider, independently reviewed; keys alone grant no permission |

One dollar = 1,000,000 micro-USD. Rates differ by provider/model; configure a safe bound from current official rates, including input/images/history and the 2,000-token output cap. Unknown rates mean keep the budget at zero. The administrator cost setting is a policy assertion; this pilot cannot prove a user-supplied rate bound against a live bill. No provider has been contacted in tests.

Extraction review grants only `extract` permission for the exact source/version/crop/provider. In the selected Tutor conversation, **Review cloud answering scope** and **Approve reviewed scope** grant `answer` permission for 15 minutes. Source, provider or scope changes require review. **Revoke permission** blocks future calls and pending matching work; it cannot recall transmitted data. Maximum context is 64 KB; output is bounded to 16,000 characters. Redirects and automatic network retries are disabled for multimodal calls.

A `sending`/`outcome_unknown` record conservatively retains its reservation. An identical dispatch cannot be silently repeated. Inspect the ledger/provider billing before making any explicitly new paid attempt; no automatic refund/reconciliation claim is made. Missing dependencies/key, budget, source change or failed parsing retain originals and show a blocked state.

Official capability/privacy references checked 13 November 2026: [image input guide](https://developers.openai.com/api/docs/guides/images-vision), [Chat Completions reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create), [structured output](https://developers.openai.com/api/docs/guides/structured-outputs), [data controls](https://developers.openai.com/api/docs/guides/your-data). `store=false` does not promise zero provider retention. JSON schema validity does not prove faithful mathematical transcription.

## Ownership, backup, restore and rollback

Native Library remains authoritative for originals, selections, consent receipts, corrections, artifacts and supplied lecture manifests. Canonical SQLite remains authoritative for knowledge chunks and Tutor exchanges/snapshots. Retrieval generations are disposable. No automatic Assessment, Learning Studio, Planning, grades, Notes or external Obsidian-vault writes are introduced.

Activation checks existing owners and schema checksum; creates verified SQLite online backups, copies original assets and other files under the academic data root, and writes a SHA-256 manifest before applying additive tables. App/writers must be stopped to coordinate these independent owners. Nested symlinks are refused. External owners/vaults/configuration outside that root require their existing independent backup. The returned backup directory contains `academic.sqlite3`, `library.sqlite3`, `native/blobs`, other owned assets and `checksums.json`. Keep that directory private.

Restore drill: copy those backups to a separate empty scratch directory, copy `native` to a cloned `native_library`, place `library.sqlite3` there, then run `PRAGMA integrity_check` on both cloned SQLite files and verify each copied blob against `checksums.json`. Use the cloned stores for verification only. Automated activation tests execute integrity and old-reader compatibility on synthetic owners; never overwrite current study activity with a stale backup.

Primary rollback: stop app, remove/set `ANVAYA_MULTIMODAL_ENABLED=false`, restart the same verified build. Optional tables/history remain. Other text-only records retain their existing path; selected derived evidence is excluded while disabled. Native schema remains 2 and old Native reader acceptance was checked on synthetic upgraded stores. Full old-build downgrade compatibility across every independent owner is not certified. Do not use database deletion as an index reset or routinely restore old backups over newer records.

See [validation.md](validation.md) for actual commands, results and limits.


## Completion update

The reader now supports normalized crop selection for images/PDF pages, visible crop boundaries, review invalidation after edits, restored matching selections after reload, and multiple supplied frames. A PDF page never inherits another page's processed selection. Zoom remains available with crop overlays. New lecture links open at the first real cue even when the transcript begins after zero.

Run repeatable offline validation on your own Windows machine with the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-assessment-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m scripts.multimodal_validate --browser --output .\verification\multimodal-local.json
```

The validation command itself does not install anything, activate personal stores or call live providers. It runs isolated synthetic tests, clears provider keys from the subprocess environment, enforces a zero default budget, and records the actual OS, source revision, dirty-tree state, test exits/counts/skips and unverified live-model quality. A skip or failed suite makes the command fail. Browser installation above is an explicit optional prerequisite. Reports from Linux never claim Windows verification. No live vision test or video/ASR capability is implied by a passing offline report.
