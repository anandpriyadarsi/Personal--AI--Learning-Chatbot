# Learning Studio self-contained ZIP format (local website)

This format removes the need for manually registering professor PDFs or using a
separate binding script. It is **not** an Android APK import format.

## Archive structure

```text
bundle.json
modules/theory/module.json
modules/theory/source.pdf
modules/theory/assets/theory_page_01.webp
modules/lab/module.json
modules/lab/source.pdf
modules/lab/assets/lab_page_01.webp
extras/Google_Colab/UC100N_Week6_Lab_Practice.ipynb
extras/Study_Resources/Rapid_Revision_and_Viva.md
```

`bundle.json`:

```json
{"schema": "anvaya.learning-bundle.v1", "modules": ["theory", "lab"]}
```

- Each module contains a canonical `anvaya.learning-module.v1` or `v2`
  `module.json`, with the same fields and revision rules as ordinary authored
  packages. The `source.sha256` must match the unchanged `source.pdf` bytes.
- `source.source_id` is overwritten with `portable.<full SHA-256>`; never
  pre-register a source ID. `source.filename` preserves the original PDF's
  display name. The original source bytes are preserved as an immutable
  Learning Studio snapshot.
- `modules/<slug>/assets/` files use the same content and identifiers as
  standard canonical ZIP assets, e.g. `assets/theory_page_01.webp`.
- Optional `coverage.json` is checked using the existing strict coverage
  validator and must refer to the finalized module/source identity.
- Optional `extras/Google_Colab/` and `extras/Study_Resources/` may contain
  only `.ipynb`, `.md`, `.csv`, `.json` study files. These are inert and
  **not executed, interpreted as code or persisted** by Learning Studio.
  Students retain them by saving/extracting the original ZIP.
- The ZIP uses existing bounded archive readers: at most 25 MB compressed,
  30 MB expanded, 4 MB per member, 550 members, and no traversal, symlinks,
  encrypted entries or unapproved filenames. Maximum eight modules.
- A module's course/topic mapping remains subject to exact course catalogue
  validation. Unmapped authored modules appear in Unmapped until mapped using
  the existing course-mapping UI; no guessed course IDs are invented.

## Use

On the updated local ANVAYA website open `/learning/import`, choose the
self-contained ZIP, and press **Validate and stage learning package**. All
modules and original PDF hashes are validated before any write; staging then
occurs in a single Learning Studio SQLite transaction. A page presents each
module's independent review link. Publish each module only after reviewing its
lessons, questions and source pages.

Existing canonical JSON/ZIP imports keep their current registered-source
requirements; self-contained ZIPs do not change the global Library or
`knowledge_documents` registry. The Android-only Vedic adapter is unchanged.
