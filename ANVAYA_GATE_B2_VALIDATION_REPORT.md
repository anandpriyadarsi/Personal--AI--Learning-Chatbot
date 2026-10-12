# Gate B2 validation report

Source baseline: `6d2c3a01d6deca5b64bfc19ce2041769a8b00929`. Feature: `anvaya/topic-intelligence-b2-read-safety`. Reviewed implementation `ce2a770d9358fad1e00b0032436a8f3f46da7ac6` has observed Ubuntu/Windows and aggregate PASS. Main remains `f859a3c7cdf44baadc17d9bd1a6c656530c1b5bf`, unmerged. This report's evidence-only successor commit changes the three required Markdown reports; its exact tip/run is independently checked before delivery and recorded in the archive. GitHub recovery uses this branch's SHA and its matching Actions run.

## Executed pre-publication checks

- Baseline route probe: both seeded GETs created learning_memory.json/.tmp; empty cases produced no write. Original JSON evidence retained outside source.
- First desired B2 test run:8 failures/8 passes, before product edits. RED log retained.
- Expanded focused run:105 passed (23 B2,45 unchanged B1,20 authority-routing,17 characterization tests). No failures/skips after test setup corrections. A named URI argument in a tracing wrapper initially collided with sqlite3's uri=True; corrected in the fixture, not product code.
- New browser checks: four real viewport tests passed; independent reviewer also repeated4 successfully. Initial failed focus assertions were on closed navigation/disclosure and were fixed by exercising their actual keyboard controls.
- B1 DTO/repository/test bytes compared with git show at the exact B1 SHA; all unchanged. All14 migration SQL files compared with base; no migration allocated.
- Nonmutation tests include full protected file digests, SQL iterdump, SQL authorizer mutation attempts, query-only CREATE refusal, committed-WAL read visibility, repeated previews, integrity and foreign-key checks on disposable DBs. No production source/control/vault/provider configuration enters exported validation.

## Full validator and independent review

Use the existing CLI `python scripts/architecture_validation.py --output <new-external-directory>`; hosted jobs require --require-clean. Full pytest has no -k/deselection/blanket skip. The separate browser category retains all39 existing checks and adds the four B2 viewport checks. Existing original focused tests, both fixture orders,17 characterization checks,20 Node tests, dependencies/compile/migration/checksum/diff gates remain.

Publication required complete local validation and independent review before each product/harness commit. All formerly pending implementation gates are resolved by the observed final correction evidence below. Evidence from earlier snapshots is retained as history, not substituted for exact-source acceptance.

Raw logs/XML, exact source manifest, CI evidence/links and SHA256 manifest are delivered in the final attached archive. Essential final outcomes are appended here after hosted execution; reports alone never certify installed Windows authority.

Review repair regressions:9 RED/29 PASS before corrupt-course and symlink-parent fixes. The pre-CI-correction review had40 non-browser cases plus4 viewport cases; final B2 has42 plus4. These additions do not change B1 or migration bytes.

Independent final review:169 affected tests passed with zero failures/errors/skips. All Important findings resolved with regressions; no Critical findings. The final store/control guards add2 cases; B2 total40 non-browser +4 browser. Initial full validator snapshot precedes those final guards and is retained as superseded evidence; only the final source-matched run qualifies for publication.

## Final local validator

`run-otwil5cf`: all15 categories PASS. Full1861, focused54, both fixture orders41, characterization17, real browser43 (39 retained +4 B2), Node20; zero failures/errors/skips. Snapshot fingerprint `f535d66051eec4b090692b48382b7cd9c71c50ad56b1a39b825d712ab53008d2`. All tested Python bytes match the prepublication source except the corrected course_manager module documentation; its entire executable AST was compared unchanged. Subsequent Markdown edits only record evidence. Hosted --require-clean runs validate the exact published commit including documentation.

Superseded `run-dbs7hvp6` passed1859/43/all15 but preceded the final store/control guards and is not final acceptance evidence.

## Hosted first result and diagnostic correction

Atfccf082, run38238560956: Windows1861/17/43 and all15 categories PASS; Ubuntu1848 passed/13 setup errors in full pytest,4 passed/13 shared fixture errors in characterization, while all43 browser checks and every other category passed. Aggregate correctly FAIL. The errors came from read_routes' no-files/no-writes assertion; its child results were not retained, so the exact original changed paths are unknown. No Ubuntu PASS was inferred.

A new injected-write regression proved failure evidence was lost; diagnostics now save/print results before both unchanged acceptance assertions and include them in assertion messages. A separate real Git gc.auto=1 regression reproduced an asynchronous .git mutation/temporary-directory cleanup race. Snapshot add/commit now disable gc.auto and maintenance.auto only via per-command flags inside the disposable repository. No inventory exclusion or product assertion was relaxed. This reproduced fixture race is not claimed as the proven original Ubuntu cause; new exact-source hosted execution is required.

Clean local published run-thg0we87 atfccf082 passed1861/43/all15 with source dirty=false and exact tested bytes. The correction adds2 tests (B2 now42 non-browser +4 browser); fresh full and independent review passed before publication.

Independent correction review:68 cases PASS; no open Critical/Important findings; exact read-safety acceptance predicates/inventories retained. Product/B1/migration code unchanged fromfccf082.

Correction local validator `run-bwa80m6b`: all15 categories PASS; full1863, focused54, both fixture orders41 each, characterization17, browser43, Node20. Every XML suite reports zero failures/errors/skips. Snapshot fingerprint `8ec01d00147cce0c52fd70e0a86e4e43fea3ebe25cfd0d74c88b79a8cbcf562c`; every non-Markdown tracked file matches the validated snapshot. This run intentionally tested staged corrections (`dirty=true`); exact clean hosted acceptance was then verified below. Synthetic migration ledger14, second apply empty, integrity ok, foreign keys empty, DB/WAL digests unchanged and logical state unchanged; normal SHM coordination is distinguished from logical mutation.

## Observed exact-source hosted acceptance

Run [38286115666](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38286115666), source `ce2a770d9358fad1e00b0032436a8f3f46da7ac6`: Ubuntu job114934791390, Windows job114934792637 and aggregate job114942081171 all SUCCESS. Both artifacts require clean source and record `dirty=false`; all15 categories PASS with exit0. Downloaded XML and logs were inspected, not just job colours.

| Check | Local correction | Ubuntu | Windows |
|---|---:|---:|---:|
| Complete unfiltered Python | 1863 | 1863 | 1863 |
| Original focused suite | 54 | 54 | 54 |
| Fixture orders, each | 41 | 41 | 41 |
| Characterization | 17 | 17 | 17 |
| Real Chromium, retained39 + B2 four widths | 43 | 43 | 43 |
| Node tests | 20 | 20 | 20 |
| Failures / errors / skipped tests | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

Chromium viewport cases are390/768/1366/1920 with actual routes, reload, keyboard focus and overflow checks. Python suites include all42 B2 non-browser cases and unchanged45 B1 cases; XML retains exact case IDs. No -k/deselections, blanket skips, weakened assertions or continue-on-error were added. pip check/freeze, compile, migration-fixture and all four source/feature diff gates passed. Synthetic ledger14, second apply empty, integrity ok, no FK violations, unchanged SQL logical state, unchanged existing DB/WAL bytes; live WAL/SHM coordination creation/SHM changes are explicitly distinguished from logical writes.

| Environment | Local | Ubuntu | Windows |
|---|---|---|---|
| Python | 3.12.14 | 3.12.15 | 3.12.10 |
| SQLite | 3.53.1 | 3.45.1 | 3.49.1 |
| Node | 24.19.0 | 22.23.3 | 22.23.3 |
| Playwright | 1.51.0 | 1.51.0 | 1.51.0 |

Tracked dependencies are used; fresh Chromium installed per hosted platform. Source fingerprints are Ubuntu `d67a90b431a2856422b1192868d54cc89ea0babd5de0329f06ac843bc9279f01` and Windows `b07e37fbad439503bba1423c6c4d64b0d3a1d707d8b0dad204ed42d887af06e6`. All B2 changed files and Python/Markdown bytes match exactly. The82 other platform digest differences were individually proved exact LF→CRLF transforms on tracked `text=auto`, unspecified-eol paths; no substantive change is accepted or hidden. Both manifests name the same Git SHA. All three downloaded CI ZIPs match GitHub's published SHA256 digests.

Available artifacts: Ubuntu11763352393, Windows11763748794, aggregate11764601431. Aggregate JSON names this exact source and both required platforms with `matrix_result=success`, `GATE_A_DEV_AUTOMATED=PASS`, `GATE_A_LOCAL_PRODUCTION_AUTHORITY=BLOCKED`. The archive includes flattened logs/XML/manifests and aggregate JSON; screenshot payloads are excluded.

Final delta is13 files from B1: three reports, four bounded loader/router modules, three validator/characterization scripts and three test files. B1 DTO/reader/test, all14 SQL migrations, full Assessment design and Windows guide remain byte-identical. Independent whole-delta169 and correction68 cases passed with no open Critical/Important findings. Handoff review additionally tightened corruption scope and both WAL/SHM sidecar wording. A/B/D/P remain FAIL product witnesses; C desired acceptance PASS. No main merge/deploy/production data operation occurred. Full B and installed production authority remain BLOCKED.
