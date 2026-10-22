# ANVAYA Mobile V1.0 — architecture and implementation plan

22 October 2026. Owner brief: private, Android-first, single-user companion.
Baseline: verified main b0f650c3f30e4c49201c2f7c2a0d7add41b34174,
tree ae3c675859c39641b13111b7a64637f10a49213c. Architecture PR #33 is
merged; Tutor PR #32 is draft and excluded. No changes to either branch.

## Design

Reuse Flask/Jinja and all academic routes, repositories and identifiers. A shared,
progressively enhanced shell adds Today / Learn / Tutor / Practice / Library
navigation on phones, an accessible secondary menu, themes and installation
help. Existing Today projections provide deadlines, proposed study and tasks;
empty and unavailable states retain their honest meanings. No mobile domain API,
new account system, new database migration or duplicated academic calculation. Existing backup-first local startup activation is preserved.

PWA selected over a JavaScript rewrite or embedded Python APK: it reuses working
academic engines and their persistence gates. A native rewrite would introduce
an unverified second owner of academic records. An APK wrapper would still need
the Python host and would not solve standalone offline operation.

Runtime: browser on Android -> authenticated TLS gateway (future deployment,
not supplied here) -> loopback Flask -> existing SQLite/services. Same-device
loopback is supported. Plain LAN HTTP/public binding are deliberately not offered.
The PWA is a browser client, not an Android Python runtime. Without a host it can
show only a generic offline/help screen; it cannot access lessons or save work.

## Increments and acceptance contracts

A. Document privacy before implementation. Add private-mobile mode, default-deny
cloud provider boundary, no-store responses and same-origin browser policy.
Test configured keys cannot override private mode, opt-in is explicit, and all
academic responses including errors cannot be cached. Preserve generic app behavior.

B. Add manifest, existing-brand 192/512 icons, safe-area layout, shared navigation,
light/dark preference (only preference persisted), install/settings screen and a
minimal worker. Cache exact reviewed nonsensitive assets and generic offline HTML
only. No API/page caching, query-string asset caching, automatic update activation,
background sync, push, client transcript storage or mutation replay.

C. Exercise actual Today, Learning, Tutor, Assessment, Library, Notes, Planning and
Analysis routes with disposable synthetic owners. Responsive overrides must be
narrow and retain desktop content, source references, assessment timers and saves.
Tutor teaching changes from #32 remain excluded. Existing server-owned progress,
transcripts and assessment pause/resume remain authoritative.

D. Test offline navigation fallback, reconnection, failed POST behavior, cache
contents, worker upgrade waiting and no outbound browser traffic. Do not reload
active pages for updates; installation help explains closing all windows after
saving/pausing. No sensitive draft persistence on the client.

E. Document installation, device/keyboard limitations and APK feasibility. Add
native Ubuntu/Windows CI; capture genuine Chromium mobile screenshots. Run full
Python/Node regression and report actual statuses, skips and blockers.

## Review focus

Worker cache must never contain academic pages or responses; updates must not
reload assessments; a phone viewport must not hide save/pause/navigation; light
theme must preserve readable lesson/math; private mode must block providers even
when host credentials exist. Cross-device transport remains blocked until an
actual authenticated encrypted gateway is configured and validated. No public
hosting is created by this branch.

## Execution ledger

- A: threat model written before product edits. 8 HTTP contracts observed failing
  for absent manifest, policies and cloud-AI gate; then passed after implementation.
- Baseline: 19 web foundation / V2.3 HTTP tests passed before mobile shell changes.
- A/B: 17 mobile/foundation contracts passed at the first increment. Existing optional HTTP provider gains
  only a lazy private-mode check; provider protocol and academic engines unchanged.
- Ruling: execute the owner-specified A–E plan inline without additional approval
  gates. The owner explicitly requested immediate implementation and a draft PR.
- Ruling: supported private prototype remains loopback-only. No safe, authenticated
  encrypted cross-device deployment is preconfigured; widening binding would
  expose private records. Phone access without an authorized host stays blocked.
- C/D: actual host shutdown/restart verifies generic fallback and failed POST
  rejection without replay. Browser installation reports no manifest errors and
  no installability errors; this is Chromium, not physical Android installation.
- C/D: real native forms reproduced Origin:null under no-referrer; changed to
  same-origin Referrer-Policy while retaining cross-origin rejection. Explicit
  Tutor exchange now persists and reopens through real SQLite with a labelled
  deterministic provider, not a live model.
- Final review: independent reviewer reproduced blocked Notes editor inline
  scripts under strict CSP. Extracted both unchanged scripts into local assets;
  permits blob image previews only (not third-party images), with an end-to-end
  formatting/template/media/save regression. No unsafe-inline script exception.
- Documentation clarification: existing display/navigation preferences remain;
  legacy session-palette preference keys include IDs, but no answer text is stored.

- Regression pass: 9 failures in the initial full run (2922 passed, four exact
  unavailable private IKS skips). Original assertions exposed generic-wrap,
  first-fold, offline-write proxy and accessible-name issues; all were fixed.
  Notes source checks were updated to follow the extracted asset, not removed.
- Targeted final first-fold: 2 passed. Intermediate protected/mobile gate: 118
  passed. Final full and native gates are recorded separately in PR checks.
- Worker refinement: non-GET requests are never intercepted; application/native
  network failure handling retains authority. Generic navigation fallback only.
