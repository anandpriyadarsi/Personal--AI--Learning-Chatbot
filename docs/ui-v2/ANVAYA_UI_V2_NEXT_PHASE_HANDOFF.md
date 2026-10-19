# Next phase handoff

ANVAYA UI V2 — FEATURE BRANCH READY FOR INTEGRATION: NO

PR: https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/pull/26 (draft). Branch: `feature/anvaya-ui-v2-home-obsidian-workspaces`.
Verified integration base: `ce2e4e06175f76778f114a85f7552160aeb08a99`. Runtime-tested source: `b19ead6d280c9098b53a637222235407ed28889d`, tree `721e365c2e18261451334f51978e1254dba71ca5`. The final report/screenshot commit preserves those runtime and test bytes. See CROSS_PLATFORM_ACCEPTANCE for completed exact-source runs and PR #26 for final-head outcomes.

## Delivered and deferred

Home, Obsidian vault/reader, personal Notes library/reader/editor and Knowledge search/reader now use an opt-in dark workspace system. Courses/Resources receive selected improvements. Real before/after proof and independent engineering/UX reviews are linked in [the evidence index](README.md). All seven engineering and five Important UX findings are closed; minor mobile density/table cues/glyph limitations remain documented. Vault Notes compatibility has route coverage but less direct browser coverage and is PARTIAL. Calendar/Tutor interiors, template galleries/reconciliation/legacy diagnostics, advanced editor interactions, and physical-device/assistive-technology audits are DEFERRED.

## Integration gates and exact order

1. Keep this PR draft until the existing strict architecture gate is resolved by its validation owner. Both hosted platforms report no failing tests but four absent external Learning pilot fixtures. Do not disable the zero-skip gate or copy private fixtures to GitHub. UI browser106/full2501+4skip and Assessment455Python+24Node already pass on both platforms for the tested source above.
2. Fetch current main and the branch and compare the new main SHA with `ce2e4e06175f76778f114a85f7552160aeb08a99`. Main was unchanged on 19 October. Planning V2.1 and automatic WAL snapshot work are already included in that base; no competing Planning branch was merged here. Reconcile any later Planning changes with their owner, preserving their templates/services and academic authority rules.
3. Learning Studio visual PR #20 remains open and separate at `10cf1b0ef34049f0633f5b8da396f8f8eb630794`. Do not merge it as a convenience. Its recorded shared app.css/base additions must survive eventual integration. Our app.css/app.js are unchanged; base.html adds empty extension blocks and workspace_base.html supplies opt-in assets/search/nav. Reconcile these additive base blocks explicitly rather than replacing either shell.
4. Review the diff and before/after evidence. Confirm no product routes/services/schema/data changes, scoped CSS only, explicit form actions, and separate personal/vault Notes authorities. Retain the test-only installed-launcher backup-path fixture repair and its original integrity assertions.
5. After any actual integration/rebase changes, rerun the focused Chromium zero-skip gate, full suite, protected browser controls and Assessment preservation on Ubuntu and Windows. Require actual results for the intended integration source. Main merge and deployment need a later explicit user instruction.

## Reproduction and rollback

Install `requirements-learning-studio.txt`; run `python -m playwright install chromium`; set `ANVAYA_BROWSER_TESTS=1`. Run `python -m pytest -q tests/test_ui_v2_browser.py tests/test_ui_v2_protected_browser.py`, full pytest, and `node --check personal_learning_assistant/ui/web/static/js/workspace_v2.js`. Capture synthetic proof with `python scripts/ui_v2_capture.py --output <outside-repo-evidence> --widths 390 1366`. No personal vault or database is needed.

The branch has no data migration. Before merge it can remain isolated or be closed without changing main. After a separately authorized merge, revert the UI commits as source changes, preserving later owner changes; do not roll back academic records or vault content.

To adopt the system in an independently owned page, review with that owner before extending workspace_base.html. Keep feature-specific styles scoped; preserve projections and repeat that page's controls, responsive/keyboard and source-safety checks. Do not globally import workspace assets into protected pages.
