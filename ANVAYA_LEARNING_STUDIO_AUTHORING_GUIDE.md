# Learning Studio authoring guide

Use the actual `ANVAYA_LEARNING_STUDIO_IMPORT_SCHEMA.md` and coverage contract, rather than inventing a schema or production source ID. The checked-in `examples/learning-studio/module.json` and `synthetic-source.pdf` are a complete, explicitly synthetic V1 canonical example. They preserve 20 pages, teaching blocks, full revision, recall and private MCQ keys. V2 relational graphs and trusted activities are additive and require their exact validator contract. No HTML, imported SVG, JavaScript, executable widgets or external assets are allowed.

1. Obtain the registered original PDF, exact existing source ID/hash/page count and a read-only export of registered course/topic candidates. Keep original bytes unchanged. If registration is unavailable, author source-first/unmapped; the synthetic `demo-source` is usable only in the disposable demo.
2. Preserve every page and source extract. Give each lesson stable IDs and exact source-page references. Full notes must preserve list members, comparisons, classroom shorthand, equations, tables and uncertainties. Put original claims and added teaching in separate blocks. A citation being in range does not prove it supports the answer.
3. Draft a separate `anvaya.learning-coverage.v1` companion ledger using the implemented coverage validator. Inventory meaningful text and visually inspect nontext elements. Record exact locators, mappings or unresolved reasons; do not call token overlap semantic verification. Keep fidelity, external factual verification and academic mapping independent.
4. Include complete revision plus source-linked recall cards; author activities through the trusted registry only. Questions need distinct choices, a private zero-based correct index, explanation and supporting pages. Never put keys in public client payloads. Ungraded reflection/reveal is engagement, not correctness or mastery.
5. Validate before staging. Review unresolved material only; agent fidelity review is narrower than instructor approval or external historical certification. Mapping requires current registered candidates, review and confidence ≥0.90; never fabricate a topic ID.

Read-only preflight (same arguments in Bash and PowerShell):

```text
python scripts/learning_studio_preflight.py examples/learning-studio/module.json --source examples/learning-studio/synthetic-source.pdf --source-id demo-source
```

For a real canonical bundle, replace all three input arguments with the actual package/original/registered ID, and pass `--catalogue catalogue-export.json` for a reviewed mapping. Missing catalogue accepts unmapped packages only. Errors fail before any store write; source mismatches are never repaired by rebinding a checksum. Preflight uses the same strict schema, references, asset, archive, source hash/page and importer limits; its report separately shows mapping/review/coverage disposition. `--export NEW.zip` creates a new canonical archive after success and refuses overwrite.

Private pilot normalization:

```text
python scripts/learning_studio_preflight.py recovered-private-pilot.zip --pilot --revision 2 --source registered-original.pdf --source-id EXACT_REGISTERED_ID --coverage exact-version-coverage.json --export new-private-canonical.zip
```

This invokes the V1.2 normalizer on top of the current strict pilot adapter, restores all twelve recall cards and trusted teaching additions into a new V2 revision, not pasted JSON or executable prototype HTML. The embedded original must equal the supplied original. The adapter may add versioned teaching enhancements; existing source and original question identities are retained. The optional `--coverage` companion is validated against the exact module revision, source hash and full package digest; a ledger built for `pilot-source` cannot be silently reused for another source ID. Rebuild/review the ledger for a different registered identity; never rewrite its digest merely to force acceptance. Stage/publish the output through the normal guarded importer in a disposable environment first. Do not commit private lectures or candidates to the public repository.

Use `ANVAYA_LEARNING_STUDIO_AUTHORING_PROMPT.md` for repeatable ChatGPT drafting. Imported package keys remain private authoring material. Reader projection removes MCQ keys and explanations before answering; recall answers are deliberately revealable ungraded teaching material.
