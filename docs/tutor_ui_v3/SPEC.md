# ANVAYA Tutor UI V3 — Mobile-First Redesign, Android Integration & Optional Online AI

**Date:** 23 October 2026
**Repository:** https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot
**Execution:** ChatGPT Work, with connected GitHub and a disposable/synthetic test environment
**Approval rule:** Do not merge to `main` without my explicit approval.

## 1. Mission: implement, don't stop at an audit

Continue ANVAYA from the **latest live GitHub state**. Modernize the actual Tutor user interface into a clean, premium, mobile-first, chat-centred learning experience **on desktop and in the standalone private Android APK**. Preserve all Tutor V2.3 academic intelligence and existing ANVAYA learning, assessment, library, notes, planner, backup, and privacy behaviour. Provide a tested, installable Android APK rather than a mockup, image, disconnected React demo, PWA-only change, or wrapper requiring my laptop.

I find the existing Tutor interface old-fashioned, dense, and difficult to use on a phone. The desired experience is an elegant learning companion called **ANVAYA Tutor / Alex**, not a generic administration dashboard. Favour calm, dark-first, professional, modern typography, spacious conversational reading, subtle teal accents, accessible controls and a high-quality light mode. Be original; do not copy ChatGPT or Claude branding/assets.

**My decisions:** (1) Android screenshots and screen recording must work normally; (2) local storage stays private; (3) I accept an **optional online AI connection** when it is required for genuine generative tutoring, provided I explicitly configure and enable it; (4) offline lessons, notes, existing transcripts and deterministic academic features must remain functional without internet; (5) no public hosting, paid infrastructure or forced cloud sync.

## 2. Confirmed starting points — verify before editing

- `main` contains merged **Tutor V2.3 PR #32**. Its newer Tutor templates are materially different from Mobile V1.1's older templates. Do not accidentally overwrite the newer Tutor implementation while integrating Android.
- **Mobile V1.0 PR #34** and **standalone Android Mobile V1.1 PR #35** form a stacked, unmerged draft series. PR #35 head is `feature/mobile-v1-1-private-android-runtime-2026-10`, based on the Mobile V1.0 branch; this is the existing real embedded-Python/Flask/SQLite Android application. **Continue it, do not restart.**
- On 23 October, screenshot restriction `FLAG_SECURE` was removed from `android/app/src/main/java/in/anvaya/privateapp/MainActivity.java`; the instrumentation's screenshot-bypass was replaced with an assertion, and the Android build/security documentation was updated. Latest observed PR #35 head after these three commits: `ddf336ef1e1f2d01bb833eb11f7a5e4010d8bead`. **Check the current actual head; do not revert, reintroduce the flag or duplicate the work.** The previous APK predates these commits and does not demonstrate owner-enabled screenshots.
- Source areas inspected: `personal_learning_assistant/ui/web/templates/agent.html`, `agent_session.html`, `base.html`, `static/css/app.css`, `static/css/tutor_readability.css`, `static/js/tutor_chat.js`, `static/css/mobile_v1.css`, `personal_learning_assistant/tutor/http_provider.py`, `personal_learning_assistant/android_runtime.py`, Android `MainActivity.java`, and `docs/mobile/v1_1/BUILD_AND_SECURITY.md`.
- Current `main` Tutor session already has adaptive teaching state, current goal, pending diagnostic/exit question, prerequisite repair, practice level, optional memory review, persisted turns, source evidence and links, feedback, safe local maths rendering, CSRF tokens, request-id deduplication and five teaching follow-up prompts. **Preserve these, including their underlying behaviour.** The Android branch may lag these features and needs safe reconciliation.
- Android V1.1 currently denies non-loopback Python networking, rejects external WebView origins, and disables online generative AI. It uses an app-private Python/Flask backend, SQLite and an authenticated random-port loopback channel. Online AI will require deliberate backend adaptation, not just a new toggle or API-key input.
- Existing Smart Verification work and accepted changes on `main` must not be lost. Confirm status of any concurrent branches/PRs before selecting an integration strategy.

## 3. Audit and integration phase (mandatory, then implement)

First inspect latest `main`, PRs #32, #34 and #35, working-tree state, route contracts, existing Tutor tests and actual UI. Capture baseline **authentic, running application** screenshots in disposable synthetic fixtures at 360px, 390px, 768px and 1366px; where possible include Android API 31+ emulator WebView. Record a concise issue ledger before coding. Compare mobile and main Tutor templates; map all backend fields, POST actions, CSRF/request-id expectations, local math and memory state before merging styles/templates.

Reconcile the stacked Android branches and merged Tutor V2.3 without force-pushing existing PRs, overwriting current work or silently cherry-picking stale templates. Create an appropriately scoped integration branch / draft PR based on verified refs, or update the existing feature branch only when safe, with clear base and dependency documentation. Keep both the old offline Android behaviours and the newer academic engine. No database reset, data loss or blanket disablement of academic features.

## 4. Required UX redesign — real templates and CSS/JS

### Tutor home / starting experience
- Present a clear, compact **ANVAYA Tutor** heading with visible online/offline/provider state; avoid a towering hero and stacks of dense dashboard cards.
- Make **Start learning / Ask a question**, active/recent sessions and course/topic choice the most prominent actions. Keep the Adaptive Mentor and advanced source settings, but show them through a sensible secondary section or expandable controls.
- Simple course-aware starters (e.g. explain a concept, guide me through a problem, quiz me, revisit a mistake) must be real actions, not inert decoration. Do not fabricate curriculum coverage.
- Clearly explain Source Only vs Source First in plain language and accurately display whether a configured AI provider is available. Show honest empty/loading/error states.

### Tutor conversation (highest priority)
- **Chat first:** render conversation near the top rather than placing four metrics, an entire Learning Journey and memory-management panels above it. Use a compact sticky context bar showing course, topic, mode and source policy; place detailed learning state/history/memory in accessible collapsible panels, tabs or drawers.
- Visually distinguish student and Tutor messages with an elegant, readable layout, rather than nested identical `dashboard-panel` cards. Preserve turn order, role, timestamp, answer provenance, and persisted history.
- Keep the user's current diagnostic, hint request, practice step and exit check visibly connected to the conversation. Distinguish guidance from assessed learning evidence; never turn inferred understanding into an official grade or mastery claim.
- Render safe, legible markdown, lists, code, tables, symbols, matrices and equations using approved/local rendering. Protect against XSS, broken formulas, horizontal overflow, inaccessible source links and long transcripts. Keep source citations tappable and traceable to the real local Library where available; make detailed citation and model metadata expandable instead of visual clutter.
- Persistent, keyboard-friendly input composer at the bottom of the conversation, with an auto-growing textbox, clear send action, and compact **Hint / Quiz me / Check my understanding / Explain differently / Worked example** chips. Make chips work with the existing explicit-submit semantics. Do not auto-submit a prompt without an intentional user action.
- Correctly handle Android WebView resize, IME opening/closing, scroll restoration, safe areas and the mobile bottom dock. No hidden send button, keyboard overlap, accidental double send, or losing an unsent draft during a provider failure. Preserve request IDs, CSRF and server-side idempotency.
- Feedback should be discreet but functional. Give the student access to review any learning-memory candidate with explicit approval/rejection; do not silently create memory or mutate grades/mistake logs.
- Add coherent online/connecting/receiving/error/offline states based on real backend state. Do not simulate streaming; implement it only if genuinely supported and tested. If a request fails, show a recoverable error, keep the student's text and protect saved history.

### Design system and accessibility
- Modern dark-first palette, restrained teal accent, harmonious typography, thoughtful spacing/radius/shadows, high-quality light mode and locally bundled resources. No external fonts/CDNs/trackers.
- Responsive 320/360/390/430px phone, 768px tablet and 1024/1366px desktop. Meet touch target, keyboard navigation, visible focus, semantic labels, contrast, screen reader live messages and reduced-motion expectations.
- Build scoped styles/components for Tutor; avoid destabilizing Assessment Studio, Learning Studio, Library, Notes, Planner or global styles.

## 5. Optional online AI on a private Android phone

Implement a real, owner-controlled **Online AI / Offline** choice. Offline is the default; existing supported non-generative/source-based learning and saved data must work in airplane mode. Online AI is permitted **only after an explicit in-app opt-in and provider configuration**. The app may call a third-party AI provider over HTTPS from its **phone-local backend**, but must never become a public server or require my laptop to remain on.

Reuse the existing `OpenAICompatibleTutorProvider` and Tutor engine if compatible. Support a practical BYOK provider flow such as an OpenAI-compatible endpoint (e.g. an owner-selected OpenRouter model) or other supported provider adapter. Select verified, currently supported free/affordable models when possible; **do not claim a model is free, available or within quota without checking**. Allow provider/model settings to be changed without editing the APK. GitHub Actions secrets used for Tutor tests must **not** be assumed available on the phone or baked into the APK.

Design the minimum safe outbound network exception for configured HTTPS provider requests. Keep the random-port loopback host/Origin/capability-cookie boundaries, WebView's external-origin block, no JS bridge, no public bind, and app-private academic DB. Prevent arbitrary endpoints, SSRF to private/loopback/metadata addresses via the provider setting, credential exfiltration, unsafe redirects or broad outbound bypass. Keep strict TLS verification. Request API credentials through an owner-friendly app UI and protect them at rest using Android Keystore-backed storage or an equivalently reviewed Android-native mechanism; never embed credentials in source, APK, HTML, frontend JavaScript, GitHub or logs. Provide clear key removal and connection test actions. If a secure design cannot be delivered in this increment, leave online AI visibly unavailable and explicitly report the remaining blocker rather than implement unsafe storage.

Before enabling, show a plain-language disclosure: the student's **question, selected source excerpts and relevant conversation context** may be transmitted to the chosen provider; local databases, full vaults, grades, PDFs and unrelated content are **not** automatically uploaded. Support opt-out at any time, sensible per-request context boundaries, model/request timeouts, 429/rate-limit handling, response validation, bounded retries only for safe/idempotent cases and prevention of duplicate turns or charges. Show real provider availability and failures, not misleading 'AI is ready' labels. Preserve source-grounding, error/fallback policy, diagnostic checks and all A–K Tutor behaviours; do not outsource assessment correctness to a free-form LLM.

## 6. Screenshot policy — already changed, verify in the rebuilt APK

Honor my decision to allow ordinary Android screenshot and screen recording. `FLAG_SECURE` must remain **off** on ANVAYA app windows and screenshot tests must pass **without** an instrumentation-only flag-clearing workaround. Capture genuine screenshots from the running installed APK. Do not weaken unrelated authentication, SQLite ownership, storage or network protections. Explain in settings that screenshots can contain private learning records and should be reviewed before sharing.

## 7. Tests and acceptance — no fictional PASS

Use synthetic student data only in cloud, CI and screenshots. First run targeted tests for Tutor routes, rendering, CSRF/XSS, source evidence, session persistence, adaptive diagnostics, assessment boundaries, Android local runtime, offline flows and screenshot flag, along with responsive Playwright/Chromium screenshots. Then use the existing **Smart Verification** selection and the real required Ubuntu/Windows/native Android suites on exact candidate commits, without skipping or weakening required coverage.

**Must demonstrate in actual running UI:** create a session; select course/topic and source mode; ask/answer a Tutor question; hint and diagnostic/exit-check continuity; open a source citation; persist and reopen a conversation; optional learning-memory approval; long equation/table and long conversation; no keyboard or bottom-dock overlap; provider offline/rate-limit/retry; offline notes/lessons/assessment pause-resume and backup unchanged; screenshot works in normal native activity. If online AI is implemented, run authorized real-provider smoke / A–K regression (protect credentials and avoid uncontrolled charges); deterministic fake-provider success is not a substitute for genuine provider acceptance. Preserve all outstanding external-fixture skips as skips, not passes.

Build **a new installable debug APK** from the final exact tested source, capture authentic emulator screenshots and hashes, publish it as a GitHub Actions artifact, and give installation/update steps that work from an Android phone. Explain debug-signing differences and insist on a verified backup before uninstalling/clearing storage; do not promise seamless update if APK signing keys differ. Do not publish a release APK signed with a repository-committed key.

## 8. Final deliverables and stopping condition

Deliver a draft PR containing implemented Tutor UI and any required Android online-provider integration, concise design audit, before/after real screenshots, provider/privacy threat assessment, source/commit SHAs, commands actually run, passing/failing tests and CI run URLs, downloadable APK artifact, exact phone installation and online AI setup instructions, and a brief limitations register. Preserve a clear separation between **implemented**, **verified on emulator**, **verified on owner phone**, and **not yet supported**.

Continue implementation through safe, meaningful increments. Do not finish with only a plan, visual mockup, old screenshots, or 'ready to test' claim. If the complete request is blocked, ship the largest genuine, testable increment and list precise blockers. **Do not merge into `main` until I explicitly approve.**
