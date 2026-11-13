# Multimodal educational evaluation protocol

This benchmark establishes offline application/harness behavior. It does **not** establish model accuracy, teaching quality, OCR accuracy or readiness for Windows. `model_quality=not_run`, all answer/explanation/refusal scores are null, and live path C is `NOT_AUTHORIZED`. The executable rejects `--live`; no model/API calls or paid work are performed.

Run from the repository root with the installed project environment:

```sh
python scripts/multimodal_evaluate.py --output artifacts/multimodal-quality
python -m pytest tests/test_multimodal_quality.py -q
```

Use a fresh output directory per run. Each comparison uses isolated synthetic Native Library, academic SQLite and retrieval roots. Owner databases remain under the output directory for inspection; they contain only these authored fixtures. Files in `gold/` are evaluator-only answer keys, not indexed sources, user transcriptions or provider inputs. `source_path` rejects paths outside `sources/`, and the application adapter cannot accept gold. Task IDs are manifest/report metadata and never query tokens or source text. The old token-based pilot is not used to support this benchmark's conclusions.

## Corpus and fairness

The manifest has 30 positives: six for each of digital PDF, rendered handwritten-scan proxy, rendered board-photo proxy, image-only slide and VTT with supplied frames; each subject has ten cases. Rendered italic notes and boards are explicitly synthetic proxies. They do not establish real handwriting or noisy camera-photo performance. Sources contain problems, academic definitions, code, equations or visible diagram labels. Corrected transcriptions describe those visible inputs, not evaluator solutions. Necessary chemistry definitions are supplied visibly to keep source-only questions answerable.

Fifteen negative scenarios cover N01–N15 from the approved specification. Source hashes, author and CC0 license are recorded. Six hint/incorrect-step follow-ups are run through B on existing exercises and reported separately. They are not six additional positive cases and their teaching quality is not scored offline.

Nine different held-out source assets (six images, two per subject, plus three transcript/frame pairs) are reserved and are never uploaded by the offline run. They are a diagnostic future pilot pool, not a statistically precise accuracy guarantee. Because their authors have seen these samples, an approved independent pilot should add fresh consented student samples before any final performance claim.

| Path | Actual application behavior | Meaning |
|---|---|---|
| A | Disable multimodal feature before source ingestion; native extraction, current UnifiedSearchRuntime and GroundedTutorService | Actual current text-only path, not a filtered projection of B |
| B | Enable multimodal feature; exact-location user-reviewed source content, transcript/frame manifest, current Tutor, immutable snapshots and original resolver | Corrected evidence routing, not automatic recognition accuracy |
| C | No adapter invocation | NOT_AUTHORIZED, never zero or a pass |

A and B receive the same original bytes, natural question, top-k 10 and context limit 12,000 characters. A runs before B; this fixed order is recorded. Source selections and caches cannot leak across arms. B may have source-only visual evidence unavailable in A; this is precisely why unsupported modalities are reported separately. Fake-provider output is a fixed nonacademic acknowledgement with only application-provided evidence labels. It does not solve, paraphrase or encode any benchmark answer. For an explicit matrix-computation request, the fake supplies a verified identity-copy envelope for a matrix parsed from the visible input; this exercises the existing production math gate without solving the requested operation. This synthetic formatter probe is not scored as an academic answer. Actual prompts, prompt hashes, outputs, location snapshots, source hashes, platform, SHA, dirty state and timestamps are retained.

`UNSUPPORTED` means no text modality exists in A, or semantic behavior cannot be judged using a fake provider. `NO_RETRIEVAL_MATCH` means native text was indexed but the application's natural query did not retrieve supporting evidence; it is distinct from unsupported modality and from a wrong model answer. `FAIL` means an engineering check failed (for example a stale boundary accepted, wrong citation placement or leaked crop). None of these statuses manufactures a model accuracy score.

## Automated checks and scoring provenance

* Gold-side reference arithmetic uses exact Fraction Gauss–Jordan elimination, matrix multiplication, finite loop/filter traces and directly calculated ratios/scales. It independently checks 20 numeric keys. Remaining diagram/chemistry tasks have explicit reviewer rubrics. Gold validation is reported as reference validation; it contributes zero model-answer passes.
* For positives, the actual Tutor persists evidence snapshots. The original resolver must return the exact uploaded placement/hash and the full authored page/bbox, cue ID/start/end or distinct frame timestamp/manifest. Missing snapshots and wrong identities are visible; checking only a filename or page is insufficient.
* B transcriptions are compared exactly with the authored review text. Zero edit error here means a supplied human correction survived publication, not that OCR or a model read correctly. Unmeasured automatic-recognition token/structure error is null.
* Citation-label validation rejects unavailable labels. Supported-claim citation precision remains null because the acknowledgement makes no academic claim and a fake cannot establish factual support. Raw available and cited labels are retained.
* N01–N05 submit explicit uncertainty through signed review and execute Tutor. They must clarify before any provider call, irrespective of review approval.
* N06 uses a real rotated PDF crop parser, then executes selected-source ingestion and Tutor, checking derived text **and provider payload** exclude the off-crop synthetic label; original bytes must be unchanged.
* N08 executes the temporal API at an exclusive cue end, inside a gap and at the next cue start. N09 executes production evidence selection and Tutor on 20 independently placed frames, requiring explicit incomplete/narrowing coverage, excluding the decisive last frame and clarification before provider dispatch. No fake explanation of omitted evidence is scored.
* N10 changes source metadata after signed review, requiring rejection. N11 copies the same blob into a different course and exercises the selected-source course guard. N13 tests revocation before dispatch and during an in-process response; neither can publish an exchange. N15 simulates unknown outcomes through the real reservation guard, requiring retained reservation and blocked replay. Synthetic provider probes only execute local Python methods, never HTTP.
* N07 executes the deterministic missing-board guard and must clarify without provider dispatch. N12 and N14 execute the supported production boundaries but remain `UNSUPPORTED` for language-model reasoning. N12 checks selected-source data wrapping, absence of an actually created unrelated notebook in the request and unchanged independent owner rows; N14 cannot score justified insufficiency from a non-solving fake. This is unfinished semantic evaluation, not a safety-model pass.

Sockets are denied in the harness process, monthly budgets default to zero, no vision extraction method is invoked, and providers are only in-process adapters. Test-only permission probes use synthetic reservations without any network transport or money. The report records network attempts and requires zero. Parser children run only the production bounded local extraction paths. No personal source, provider credential or learning record is required.

## Metrics and later authorized evaluation

The JSON and task CSV distinguish path statuses, exact localization, reviewed transcription equality, provider-call count, interaction burden, real host elapsed time and cost. p50/p95 cover the measured paired path runs. Python `tracemalloc` peak excludes child-process/RSS memory; it is not a Windows runtime/resource guarantee. Cost is zero for these adapters; latency is harness/application overhead, not model inference latency. Model transcription error, 0/1/2 correctness/explanation grades, supported-claim precision, unnecessary refusals and actual remote-model cost are null.

For a separately approved real-model pilot, freeze model/version, prompts and context; blind paired A/B outputs by random code and independently review correctness (0 wrong, 1 partial, 2 fully correct), explanation, all cited claims and uncertainty. Automate deterministic numeric checks but review explanations and academic claim support against the isolated rubrics. Reviewer identity, time, ambiguous adjudication and model-versus-reference provenance belong in the report. `feedback-template.csv` is optional feedback, not a requirement that the student grade all 45 tasks.

Recommended later product targets are 30/30 exact locations, at least 27/30 fully correct explanations and 8/10 per subject, at least 95% supported-claim citation precision with zero invented sources, all critical safety negatives, at most three unnecessary positive refusals, and no silently wrong accepted critical math. Serious wrong-source disclosure or silent critical-symbol corruption stops release independently of averages. None of those live-model targets is claimed by this offline report.
