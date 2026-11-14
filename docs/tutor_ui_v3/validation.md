# Fresh validation evidence — Tutor 3.0 V2

Base: `3c6dbfea860049da80358084becf5a17e97516b3`; branch: `feature/tutor-3-v2-ui`. Final tested source bytes are recorded in `screenshot-manifest.json` (SHA-256). This report does not inherit Astra's old counts.

| Gate | Actual result |
|---|---|
| Required original baseline plus optional-schema/topic-scope/notebook/teaching/Library bridge and new V2 HTTP tests | 135 passed, zero failures/skips |
| Main Chromium suite (new V2 + existing Tutor UI/Coding/final/multimodal browser files) | 81 passed, zero failures/skips, 263.00 s |
| Rendered dark/light composer contrast + exact clipboard | 2 passed |
| Supplementary 360 px multimodal stale-source journey and Coding overview recaptures | 3 passed (2 repeat existing cases) |
| Final affected route/service guards after size-check cleanup | 48 passed (repeat unit subset) |
| Node Coding + local math | 11 passed |
| Four JS syntax checks; scoped diff whitespace; dependency consistency | Passed |
| Independent branch review | Important feature-off exit and minor inactive initializer defects reproduced and fixed; no remaining reviewer findings |
| PR #81 fidelity integration | BLOCKED_PENDING_PR81; open/draft/unmerged, not imported |
| Windows/physical phone/live paid model | Not run / not authorized |

There are **84 distinct successful browser cases**: 81 main + 2 contrast/copy + 1 added 360 px multimodal case. The two extra Coding runs recapture screenshots; they are not additional distinct cases. The new V2 file contains 25 cases; the rest retain existing browser contracts. Tests cover 320/360/390/430/768/1024/1366, light/dark, short viewport, dialog keyboard/restoration, reduced motion, CSS 200% zoom plus resize, native Academic no-JS, disabled/failed Coding initialization, task/consent/export, genuine main's source stale/410 behavior, zero pre-send model calls, provider-error draft/nonce, pending state and safe rendering.

Commands used (all local, injected synthetic owners; no personal launcher):

```bash
python -m pytest -q tests/test_tutor_optional_schema.py tests/test_tutor_topic_scope_web.py tests/test_coding_notebooks.py tests/test_coding_teaching.py tests/test_library2_tutor_bridge.py tests/test_tutor3_v2.py tests/test_tutor_ui_v3.py tests/test_tutor_session_history_lifecycle.py tests/test_phase7_5_academic_agent_web.py tests/test_tutor_coding.py
ANVAYA_BROWSER_TESTS=1 ANVAYA_BROWSER_EXECUTABLE=/absolute/path/to/chromium-headless-shell ANVAYA_TUTOR_UI_ARTIFACTS=/absolute/synthetic-output/screenshots ANVAYA_WEB_ARTIFACTS=/absolute/synthetic-output/screenshots python -m pytest -q tests/test_tutor3_v2_browser.py tests/test_tutor_ui_v3_browser.py tests/test_tutor_coding_browser.py tests/test_tutor_final_browser.py tests/test_multimodal_browser.py
node --test tests/js/tutor_coding.test.cjs tests/js/assessment_math.test.cjs
node --check personal_learning_assistant/ui/web/static/js/tutor_chat.js
node --check personal_learning_assistant/ui/web/static/js/tutor_coding.js
node --check personal_learning_assistant/ui/web/static/js/assessment_math.js
node --check personal_learning_assistant/ui/web/static/js/multimodal.js
```

The final main browser invocation collected before the last two contrast tests and extra 360 px parameter were added. Those were executed separately with their own JUnit reports. Full logs and XML are in the accompanying evidence archive. The final guard subset was rerun after moving request-size validation ahead of JSON parsing. This preserves the original resource boundary for the new explicit Academic exit.

Environment: Linux, Python 3.12, pinned Flask 3.1.2 / Mistune 3.3.4 / Playwright 1.51.0 / pytest 9.1.1 / NumPy 2.4.6 / pandas 2.3.3 / matplotlib 3.10.9 / nbformat 5.10.4. The desktop Chromium binary hit an environment socket restriction; downloaded genuine headless shell 134 successfully ran the entire suite. No stub executable or browser pass was fabricated.

Interim failures: missing test-only matplotlib/nbformat packages were installed; expected newly added RED cases preceded implementation; a cache-busted-script interception fixture and an invalid synthetic citation fixture were corrected. Seven legacy assertions targeted a now-hidden redundant Conversation heading; they now measure the real transcript, retaining draft/geometry/no-auto-send checks. Final runs above are green. No unrelated full release suite or expensive Actions matrix was dispatched.

## Visual comparison

Captured the actual app and supplied Claude V2 reference at 360/1366 with external reference fonts blocked. Visually inspected mobile/desktop conversation, evidence sheets, light home and spacious Coding. The app follows the charcoal layers, quiet bubbles, blue composer, amber provenance and reading width. Deliberate differences: retain one existing ANVAYA navigation, overlay session picker, system sans fonts, stronger accessible control boundaries, real source metadata instead of fake quotes, real pending questions instead of mock scoring, main-surface Coding section navigation instead of fake execution tabs. Reference captures are labelled prototype; every production capture is synthetic real Flask.

Screenshot filenames encode surface/theme/viewport; `short-360` is 360×440. The manifest records all screenshots and source hashes. The repository gallery is a compact subset; the archive keeps the complete matrix. No pixel-equality score is claimed across different real/simulated content.
