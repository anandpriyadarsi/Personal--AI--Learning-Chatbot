# Next phase handoff

PR: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/26
Branch: feature/anvaya-ui-v2-home-obsidian-workspaces
Integration base: ce2e4e06175f76778f114a85f7552160aeb08a99
Reviewed local product commit: 12fdef072ab95a8e5829320533ab354eed0009e8
First published equivalent source: f2e956ae8cf2aea55b77540300f66d5a06d00d6a (tree675d413864e0009f89c032a34050442add9603ff, matched local tree).

Home, Obsidian, Notes/Knowledge and selected Courses/Resources work is implemented. Calendar and Tutor internal visuals, the template gallery/reconciliation/legacy diagnostic pages, advanced editor interaction redesign, and a full physical-device/assistive-technology audit remain deferred. No production install or merge is implied.

Before merge: inspect current main and the PR diff; retain Planning V2.1/WAL changes; retain Learning PR #20's separate ownership; require both focused browser and full hosted Ubuntu/Windows checks for the intended source commit; review the before/after evidence and independent review closure. No manual Windows setup is required by this handoff.

Reproduce: install requirements-learning-studio.txt, run python -m playwright install chromium, set ANVAYA_BROWSER_TESTS=1, then run pytest -q tests/test_ui_v2_browser.py tests/test_ui_v2_protected_browser.py. Run full pytest and Node --check on workspace_v2.js. Capture synthetic proof with python scripts/ui_v2_capture.py --output <outside-repo-evidence> --widths 390 1366. No personal vault/database is needed.

To adopt the design in a separately owned page later, extend workspace_base.html only after that owner's review. Keep feature-specific styles separate, preserve existing source projections, and repeat its interaction/overflow/keyboard tests. Do not globally import workspace styles into protected pages as a shortcut.
