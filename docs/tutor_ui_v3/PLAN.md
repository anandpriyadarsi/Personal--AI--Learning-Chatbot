# Tutor UI V3 Android integration implementation plan

Goal: modernize the existing Flask/Jinja Tutor in the phone-local Android application while preserving Tutor V2.3 state, storage and security.
Spec: SPEC.md. Execution authorized by the owner's instruction to implement the attached prompt; proceed inline.

Verified starting refs: main d88ab9d21481a1822951446d10e8bb1f7a8b51d9; Android #35 ddf336ef1e1f2d01bb833eb11f7a5e4010d8bead; mobile #34 99fbaeeaf9a400ff6eb0f98fa6132e0baa6ef47c. Smart Verification #37 remains separate and unmerged. Preserve merged V1.0.

- [x] Merge current main into a new branch based on Android #35. Reconcile session scripts/body class; use main's equivalent canonical SQLite snapshot fix. Do not update shared branches.
- [ ] Capture synthetic running-browser baseline at 360/390/768/1366. Audit real form contracts.
- [ ] Add route/browser regressions for chat-first layout, explicit-submit chips, failed submission draft/id preservation, source details, resizing and accessibility. Observe missing-feature failures.
- [ ] Add scoped Tutor CSS and templates: compact home, course/topic-first start form, recent sessions, secondary mentor, sticky session context, distinct messages, collapsible learning/memory/evidence, bottom composer.
- [ ] Preserve server-returned failed draft/request ID; add progressive JS textarea sizing, real submission status, guarded duplicate submit, visual-viewport keyboard layout. No browser transcript/draft storage.
- [ ] Keep Android outbound policy unchanged. Online AI remains unavailable pending a tested native Keystore credential and restricted HTTPS transport implementation, explicitly allowed by spec section 5. Display honest unavailable/provider state; no key fields that store secrets unsafely.
- [ ] Run focused then Smart Verification and canonical applicable gates. Update Android workflow to include this integration PR without duplicate full-suite authority. Build APK and run existing API31 plus Tutor native UI checks.
- [ ] Record source identity, screenshots, tests, APK hash, installation and limitations in docs and draft PR. No merge.

Review focus: provider failure after a request may be ambiguous (preserve idempotency token); long draft/code/math at 320px; tall phone keyboard; expandable memory review; Android runtime missing provider/optional memory schema. No private records, external fonts or schema reset.

## Ledger
- Main integration: two conflicts resolved without discarding either feature; clean synthetic baseline 21 tests passed.
- Ruling: retain Android offline policy and visibly unavailable online AI until native secure storage/transport can be tested; prevents shipping an unsafe credential flow. Online generative tutoring on phone remains incomplete.
- Regression RED: three new HTTP cases failed for missing UI/draft preservation; invalid-CSRF rejection passed. Existing adaptive browser journey caught composer movement during focus changes. Kept composer position across textarea→Send focus; native submit lock uses aria-disabled rather than cancelling form submission.
- Presentation tests now open the new source/feedback disclosure before using its controls. Existing evidence, provider-call counts, grade invariants, feedback deduplication and CSRF assertions remain intact.
- Independent final review: no Critical/security findings; four Important cases reproduced or identified: wide inline-math overflow, newest reply offscreen after long history, sticky context hidden under global header, and non-authoritative keyboard-open check.
- Wide-inline-matrix and long-history tests: both RED, then GREEN. Sticky header + Mentor result disclosure: three RED, then fixed. Existing academic assertions retained. Keyboard instrumentation now taps the actual field and requires native WindowInsets.Type.ime visibility before screenshot/geometry checks; CI is required to validate it.
- Minor Mentor disclosure fixed in the same presentation pass: requested course advice remains expanded after GET.
- Full local regression on the first candidate was interrupted intentionally when review changes made its source identity stale; it is not a completion certificate. The first Smart Verification invocation reported 114 pass / 70 browser-opt-in skips; authoritative browser/full runs use ANVAYA_BROWSER_TESTS=1.
- Existing scripted A–K setup needed to open the new optional-title disclosure; its teaching/mutation/math assertions remain unchanged. Its original composer-width assertion exposed a genuinely narrow phone input: Send moved to a footer so the textbox retains full form width. Unconfigured home state is explicit again. A–K + UI run: 69 passed; light/full-width checks: 3 passed.
- Smart selection with browser opt-in exposed two legacy protected-shell tests selecting the now-collapsed Mentor without opening it. Updated the user interaction, retaining no-write/no-LLM and shell assertions.
- First API31 candidate built, but installed test failed honestly because the restored synthetic workspace had no retrieval generation. Added explicit CSRF-protected phone-local lexical rebuild through the existing production index builder (read-only canonical SQLite, no acknowledgement writes/model/network). Tutor runtime uses app-private data/tutor_retrieval so backups can preserve it. Native acceptance invokes this actual owner action, then checks a deterministic insufficient-evidence response; it does not claim offline generative tutoring.
