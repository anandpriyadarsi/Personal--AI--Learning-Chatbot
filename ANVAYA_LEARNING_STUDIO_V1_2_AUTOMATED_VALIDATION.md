# V1.2 automated validation

Validated local runtime: Python3.12, pinned `requirements-learning-studio.txt`, actual Playwright Chromium. Baseline is verified V1.1 `775941c730e8160501c849bc4971e8eb178331d1`, not current main. The public CI workflow runs Ubuntu and Windows, forces browser execution, rejects unapproved skips and compares full-suite node IDs sequentially in isolated roots.

Commands:

```text
python scripts/learning_studio_validate.py --scope all --output learning-studio-evidence
python scripts/learning_studio_preflight.py PACKAGE --source ORIGINAL.pdf --source-id EXACT_REGISTERED_ID --catalogue CATALOGUE.json
python -m personal_learning_assistant.learning_studio.demo --directory learning-studio-demo
```

Local private inputs use `ANVAYA_TEST_RECOVERED_PILOT_ZIP` and `ANVAYA_TEST_BAD_V3_ZIP`; ordinary readers and public CI do not need them. The immutable recovered ZIP is `e26d03de4a300dda0186ee005745d98afa41f0a23d12d6612965079e995f6923`, original PDF `75cd41956da56018967fea70ae5829803a9b54effa827e25883ac184bffcf411`.

Executed complete local run before the final added public synthetic browser case:173 feature passed,0failed,0skipped;101 focused passed; full baseline1792passed/16failed/0skipped versus feature1889passed/the same16failed/0skipped. No newly failing, missing or newly skipped cases. Subsequent public activity/recall/source request browser gate:10passed. The final current feature/full counts and final exact pushed-SHA CI URLs are supplied in the private acceptance evidence; this report does not fabricate future CI conclusions.

A prior bare full invocation omitted the required browser flag:16baseline failures remained, but nine newly skipped browser cases correctly made the regression-delta gate fail. This historical red run is retained; the required runner invocation corrected its environment without weakening assertions. Early integrated failures also preserve exact source-ID fixture mismatch and source Resume optional-query regression evidence. Malformed type, concurrent migration and cross-section recall defects have fail-first regression records.

Browser gates cover1920,1536,1366,1024,768,390,360widths; normal/collapsed/Focus/Contents/history/Exit, no storage/noJS notes, long titles, selected lesson/page/question, exact resume, ungraded activity action/reveal/save/reopen, recall cross-section revisit, private original previews, bounded image requests and print controls. The existing shell has a fixed dark theme; no light-theme switch exists to claim a second theme was tested. Synthetic screenshots are suitable for public CI; actual lecture screenshots remain private.

Public CI may skip only the four existing external attachment cases, each named in JUnit: bad V3 rejection, recovered strict import/durable evidence, recovered unmapped demo, recovered real browser. They are not counted as executed private-pilot Windows validation. All built-in V1.2 tests execute. Raw full-suite baseline failures remain red even when scoped/delta CI passes.

Actual private-source Windows import is NOT RUN without an existing authorized private runner. There is no mandatory routine manual Windows layout step. No new provider credentials or production fixtures are requested.
