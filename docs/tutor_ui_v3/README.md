# ANVAYA Tutor 3.0 — local web review

This branch adapts the owner's second Claude prototype using the supplied V2-amended blueprint. It keeps the existing Flask/Jinja application, Tutor teaching services, safe Markdown/math, session storage, source-policy contracts and genuine Coding task/consent/export machinery.

## What changed

- Compact scope header, bounded 780 px answer column, charcoal/blue/amber hierarchy, light theme, two-row mobile composer and existing ANVAYA navigation.
- Searchable overlay of the current **20 most recent nonempty conversations**, with persisted rename and native fallbacks. Filtering does not search all history or write records.
- Native modal sessions/evidence panels with focus containment, Escape, backdrop close and focus restoration. Evidence remains an overlay at all widths to protect reading space.
- Answer-specific cited/retrieved metadata and current scope; no fabricated quotes or source counts. Legacy locations explicitly remain unavailable. Existing original/evidence links remain the no-JavaScript fallback.
- Teaching Tools only edit the visible draft and require Send. Real pending questions remain; no client grader or mastery claim.
- Existing Coding fields now occupy the primary reading surface. Code / Review / Tasks are navigation groupings of the live controls, not a replacement state machine. Back to conversation changes presentation only. Active dispatch/task remain labelled beside Send.
- Saved Coding Send is disabled until handlers finish initialization. An explicit protected switch to Academic works even if Coding is disabled or its optional schema is absent. No schema is created. Completed sessions do not mount orphan Coding controls.
- Coding transcript replacement clears stale evidence and rerenders local math/copy controls. Clipboard denial gives a manual-copy fallback.

## Deliberate adaptations

System fonts replace the prototype's network fonts. The existing ANVAYA sidebar and mobile dock remain. The prototype's permanent second session rail becomes an overlay. Necessary control borders are stronger for contrast. Coding takes the main surface rather than a narrow rail, with section navigation rather than tabs hiding mandatory consent. No mock upload, Python runner, fake progress, generated citation, timer, quiz key or Colab success message was reused.

Automated MCQ grading, a level selector and Copy LaTeX are deferred: existing Tutor pending questions do not supply a trusted selectable-answer authority or exact per-expression LaTeX mapping. Existing math rendering, exact code copying and prompt-only teaching actions remain available.

## Dependency and limits

PR #81 was open/draft/unmerged at `a1ae1ed31412bbaff7a16ef9f78394a89845e58d`; main was `3c6dbfea860049da80358084becf5a17e97516b3`. This UI branch does not import, merge or cherry-pick #81. Its multimodal fidelity/coverage/unresolved-span integration gate remains **BLOCKED_PENDING_PR81**. After a separately authorized merge, reconcile its `agent_session.html` changes and run its actual offline validator; do not infer those results from current-main browser tests.

Tests use temporary synthetic owners and providers, never the installed personal launcher. They do not certify live AI/vision educational accuracy. Actual Windows, physical Android keyboard/device, and browser-native zoom are unverified. CSS 200% magnification, responsive reflow, reduced motion and short viewport are exercised in Chromium.

No personal migration, store activation, paid API call, Android development, main merge or workflow change was performed. An independent branch review found the feature-off exit and inactive-session defects; both have reproducing tests and fixes.

See [validation.md](validation.md), [implementation-ledger.md](implementation-ledger.md), and [Windows review](windows-review.md). Screenshots and the screenshot/source manifest identify synthetic fixtures and final source hashes.
