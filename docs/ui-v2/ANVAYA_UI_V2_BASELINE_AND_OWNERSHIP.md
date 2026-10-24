# Baseline and ownership

Initial browser baseline: `7906aa590bb663fffce8090e3d3a0158fa64c02f` (Planning/Analysis V2 merged). Before screenshots: nine real Flask fixture pages at 390×844 and 1366×768, 18 PNGs. All returned 200, with no document overflow or page errors in those baseline captures. They use disposable synthetic notes, vault Markdown and academic records.

Implementation was subsequently rebased without conflict onto verified `main` `ce2e4e06175f76778f114a85f7552160aeb08a99`, including Planning V2.1 and owner-published WAL snapshots. Those backend changes do not alter the captured baseline templates. Learning reader visual refresh PR #20 remains independently owned; it is not incorporated here. B3 PR #13 and C0 PR #9 remain distinct.

| Surface | Route / template | Screenshot-backed defect | Ownership and change |
|---|---|---|---|
| Home | `/`, home.html | Oversized launcher, equal pills, repeated Analysis summaries | This branch: action + obligations + described destinations |
| Vault | `/obsidian`, obsidian.html | Connection machinery ahead of search | This branch: compact configuration disclosure and readable results |
| Vault reader | `/obsidian/note`, obsidian_note.html | Weak reading rhythm, floating tool overlap | This branch: reading measure, focus, toolbar tools, keyboard tabs |
| Personal Notes | `/notes`, anvaya_notes_* | Source boundaries unclear, filter/card hierarchy | This branch: separate source identity, dense mobile filters, reader/editor hierarchy |
| Vault Notes compatibility | notes_library/notes_reader/notes_editor | Nested main and dense context | This branch: semantic content + secondary disclosures; original store/actions retained |
| Knowledge | `/knowledge`, knowledge*.html | Nested cards and diagnostic vocabulary compete with query/results | This branch: query, source result, reading and native disclosures |
| Courses / Resources | `/courses`, `/resources` | Endless expanded topic lists / form-heavy library | This branch: course outlines + consistent resource controls |
| Planning / Analysis | Their own templates, services and CSS | Regression inspection only | Separate owner; no product edits |
| Learning / Assessment / Tutor | Existing Studio and Tutor templates/services | Regression inspection only | Separate owners; no internal edits |

Shared dependencies: existing app.css/app.js remain byte-identical. `base.html` adds empty opt-in blocks. The original protected-page search shell remains unchanged; native GET search and expanded library navigation belong to workspace_base.html only. No private master prompt, real vault or academic database is included in this PR.
