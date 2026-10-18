# ANVAYA UI V2 implementation plan

Goal: transform Home, Obsidian and source workspaces within the existing Flask application.
Architecture: opt-in workspace_base.html, workspace_v2.css and progressive workspace_v2.js. No route/service/schema changes. Shared base changes limited to an extension block and native search form.
Spec: user-provided UI V2 redesign brief (kept private). Execution: implementation with separate browser fixture and Notes/Knowledge tasks, independent final engineering and UX reviews.

## Constraints and rulings
- Verified base 7906aa590bb663fffce8090e3d3a0158fa64c02f includes newly merged Planning/Analysis V2. Isolated branch feature/anvaya-ui-v2-home-obsidian-workspaces.
- Planning/Analysis and PR20 own their templates/services/styles. Never edit those files.
- User authorizes autonomous execution U0–U7; proceed without further design approval.
- Existing separate Notes stores remain separate. Fixtures are disposable/synthetic.
- Review focus: no-JS navigation, unavailable vs empty states, long paths, drawer keyboard focus, source immutability.
- Workspace maintenance erased the unpushed first-turn setup. No application implementation was lost. Recover from current main rather than obsolete d3fc9b5.

## Tasks
- [ ] U0 capture before screenshots from actual Flask routes at 390/1366; baseline ownership.
- [ ] U1/U2 scoped base/components + Home next action, obligations and workspace shortcuts; tests for native search, no overflow and untouched protected pages.
- [ ] U3 vault configuration disclosure; search/list and reader typography; focus mode and keyboard study tabs; real search/backlinks/save/no-JS/source safety tests.
- [ ] U4 separate My Notes/vault labels; cards/readers/editor and knowledge source hierarchy; route/form/empty state checks.
- [ ] U5 selected Courses/Resources refinements; Calendar/Tutor internals deferred.
- [ ] U6 independent engineering + screenshot UX reviews, important finding fixes.
- [ ] U7 full pytest/Node checks, Ubuntu/Windows workflow, push draft PR, exact outcomes and evidence archive.
