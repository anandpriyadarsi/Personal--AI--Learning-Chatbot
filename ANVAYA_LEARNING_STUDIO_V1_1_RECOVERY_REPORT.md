# V1.1 real-pilot recovery

**PASS for structural/source integrity and actual importer/reader execution. Semantic review remains pending.** The attached reconciled candidate was run through ANVAYA's existing strict `convert_pilot`, package validation, synthetic source-registry lookup, stage/publish lifecycle and Flask reader. Hash policy and source validators were not relaxed. No production registry or canonical course was created.

| Artifact | SHA-256 |
|---|---|
| Reconciled candidate ZIP | `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923` |
| Candidate's original PDF, expected manifest source | `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411` |
| Old inconsistent V3's enclosed PDF | `f812fb27240fc5cd5265a1608f80ac480f241b56f9b27d4826bb6453b319735b` |

The original bad V3 still raises `Pilot source hash mismatch`. The positive and negative external tests use distinct `ANVAYA_TEST_RECOVERED_PILOT_ZIP` and `ANVAYA_TEST_BAD_V3_ZIP` variables. Missing attachments explicitly skip their external tests; skips never count as actual-pilot success. The inherited ambiguous negative test was renamed, preserving its rejection assertion.

The recovered real module has **20/20 source pages, 20/20 owned previews, 20/20 lessons and 31/31 questions**. Mapping is null; every page retains `needs_review` and review flags. `demo --pilot-zip` now publishes only this single unmapped real module. It no longer clones real lecture content into synthetic registered-course fixtures. The separate default 72-module volume demo remains explicitly synthetic.

Real browser assertions verify all20 images load, exact source PDF bytes, 20 lesson/source blocks, 31 practice forms, wrong→correct feedback, retained weak history, historical related-lesson locators, print revision, no page errors and mobile overflow. Long authored Markdown tables now have an accessible bounded scroll region, after an actual-pilot mobile RED reproduction. Deterministic real-pilot desktop/mobile screenshots are in the private evidence package; lecture content is not committed to the public repository.

`docs/learning_studio/validation/v1-1/recovery.json` records preview checksums, question page references, source hash, source-registry before/after SHA, SQLite integrity and foreign-key checks. The registry hash remains unchanged by reader GETs. Both attached input ZIPs remained byte-identical. Disposable feature/source databases are the only stores used.

Execution evidence: `test_external_recovered_pilot_strict_import_and_durable_evidence`, `test_external_pilot_demo_does_not_fabricate_course_mappings`, `test_external_recovered_pilot_real_browser`, and `test_external_bad_v3_source_is_rejected`. Final local feature run: **75 passed, 0 failed, 0 skipped**, tested implementation tree `943b85eb43ee061f2e979b9f90305c315aff34ab`, pushed implementation SHA `4298c5ac65a6e3269c39c2a6b6041147150ed0b6`.

Public Ubuntu/Windows CI runs built-in synthetic security/source cases and browser coverage, with four explicitly external attachment skips. It does not prove Windows import of the private candidate. Structural success does not verify philosophical/historical claims, authored explanations or page semantics. Human semantic review and separately authorized canonical mapping remain outstanding. Automatic Tutor consumption is false.
