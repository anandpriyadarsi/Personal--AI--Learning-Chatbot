# Future source-to-lesson automation (outside V1)

V1 imports already-authored canonical packages. It does not generate presentations, perform Moodle sync or certify semantic fidelity.

1. Extend existing registered-source extraction additively. Preserve original PPTX/PDF bytes, page/slide numbering and version hashes. Extract speaker notes, tables, equations, drawings, chart data, alt text and embedded media; render local previews. The current text/XML-oriented extractor remains unchanged and must not be described as visually complete.
2. Build a coverage manifest per semantic element, distinct from byte/page availability. Image-only content, unsupported formula fragments, chart interpretation, unknown speaker notes and disputed assertions receive review flags. Source claims and teaching additions stay separate.
3. Author canonical derived packages through a bounded generation pipeline, with schema validation, exact source locators, uncertainty and explicit source-integrity gates. Stage previews before publishing. New source bytes invalidate stale previews; no automatic Notes/Obsidian or academic-grade writes.
4. Add authorised Moodle ingestion through the existing source registry: no credential scraping, unintended account access or implicit automation. Authentication, permitted courses/files and download policy need their own reviewed contract.
5. A reviewed read-only Tutor adapter may consume LearningEvidenceSummary for a verified topic and exact immutable source. Validate it against existing Tutor scenario gates before enabling. Low-stakes evidence remains supplemental.
6. Extend mathematical/visual notation with safe local rendering and editable alternatives, keeping source tracing and accessible text. Add high-fidelity visual/extraction tests separately from semantic review.
