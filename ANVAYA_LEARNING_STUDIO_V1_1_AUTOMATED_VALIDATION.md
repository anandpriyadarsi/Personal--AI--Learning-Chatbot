# V1.1 automated validation

Source: current pushed V1 base9ed585c; implementation SHA4298c5ac65a6e3269c39c2a6b6041147150ed0b6/tree943b85eb43ee061f2e979b9f90305c315aff34ab. Local Python3.12 uses the pinned requirements and Chromium. Dedicated fixtures never require a production academic database. Final documentation-tip per-OS status is recorded in the final acceptance evidence package, since a commit cannot contain its own subsequently completed CI observation.

## Local actual-source run

| Gate | Passed | Failed/errors | Skipped | Result |
|---|---:|---:|---:|---|
| Learning Studio +Chromium +bad V3 +recovered real candidate |75|0|0|PASS|
| Startup/course/Notes/Obsidian/Analysis/Assessment A–D focused |101|0|0|PASS|
| Full unchanged V1 |1771|16|0|RED baseline|
| Full V1.1 |1791|same16|0|RED whole suite|
| Full delta |0 new failures|0 new skips/missing cases|0|PASS delta|

The16 exact baseline node IDs are in `docs/learning_studio/validation/v1-1/regression-delta.json`. Fifteen rely on missing `data/learning_assistant.db`/Tutor fixtures; the shell test expects `/agent`200 when the isolated app returns503. Protected Tutor code/tests were not changed and a production academic DB was not fabricated. Regression-delta success is not a whole-suite PASS.

An earlier overlapping browser comparison yielded17 feature failures, including Assessment `test_runner_readable_with_saved_sidebar_preference[0-1280-720]`. The final sequential baseline+feature run yielded the identical16; no Assessment file/assertion changed. Initial failures remain in the private audit evidence. This transient observation is disclosed, not excluded by the gate.

## Cross-platform CI

Implementation run [38237955835](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/38237955835) runs the exact pushed4298c5a code. At documentation freeze, Ubuntu concluded success; Windows had completed isolated/browser/focused gates and was still running the full-suite comparison. Final documentation-tip workflow uses the same code/dependencies and must be checked separately at [V1.1 branch runs](https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions?query=branch%3Afeature%2Flearning-studio-v1-1). Final acceptance records the actual final SHA, run ID and separate conclusions; do not infer them from V1's green run.

| OS | Isolated/focused expectation with no private attachments | Whole suite | Final-tip conclusion |
|---|---|---|---|
| ubuntu-latest |71 passed +4 explicitly external skips; focused101/0skips |Base/feature failure and skip sets compared |Pending observation in final evidence |
| windows-latest |71 passed +4 explicitly external skips; focused101/0skips |Base/feature failure and skip sets compared |Pending observation in final evidence |

The four skips are damaged-V3 rejection, recovered import/evidence, recovered single-module mapping and real-pilot browser. Public CI does not contain third-party lecture content. Built-in checksum tampering, ZIP backslash/drive/absolute paths, symlink/bomb/path safety, stale sources, assets and desktop/mobile browser tests run on both OSes. Actual private-candidate import was executed locally; Windows actual-candidate coverage is NOT RUN on public CI. Manual screenshots are not a substitute for an incomplete CI gate.

The JUnit gate fails on errors/failures, zero cases or any built-in skip. The full-suite gate also fails on missing baseline cases or newly skipped previously executed cases, including failing external cases becoming skipped. One explicit name alias preserves the inherited damaged-V3 test identity. Tests verify these gates reject incomplete evidence.

## Reproducible commands

```bash
python -m pip install -r requirements-learning-studio.txt
python -m playwright install chromium
ANVAYA_BROWSER_TESTS=1 ANVAYA_TEST_BAD_V3_ZIP=/absolute/bad-v3.zip ANVAYA_TEST_RECOVERED_PILOT_ZIP=/absolute/recovered-candidate.zip python -m pytest -q tests/learning_studio --junitxml=learning-studio-evidence/isolated.xml
python scripts/learning_studio_junit_gate.py learning-studio-evidence/isolated.xml
ANVAYA_BROWSER_TESTS=1 python scripts/learning_studio_regression_gate.py --base 9ed585ca8e1fbcfb6f5a7e0426d030560109115e --output learning-studio-evidence/full-suite
python -m compileall -q personal_learning_assistant/learning_studio personal_learning_assistant/ui/web/learning_studio.py
git diff --check 9ed585ca8e1fbcfb6f5a7e0426d030560109115e HEAD
```

For a local old-V1 comparison with the attachment, also set `ANVAYA_TEST_PILOT_ZIP` to the same **bad V3**; that legacy fixture name belongs only to the old baseline test. CI has none of these private fixture variables. PowerShell syntax is in the optional Windows handoff.

Committed evidence: local75-case JUnit/count summary, focused101 summary, full delta, recovery checksum/reference/registry/DB record, protected tracked-file snapshot. Raw logs, fail-first records and real lecture screenshots are provided privately. `protected-snapshot.json` verifies unchanged tracked Tutor/Knowledge/Obsidian/Assessment/data files; recovery tests preserve both attachment bytes and disposable registry hashes. No production data was available or touched. Compile and whitespace checks pass.
