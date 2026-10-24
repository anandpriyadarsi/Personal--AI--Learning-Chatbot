# Assessment Studio: CBT and handwritten tests

23 October 2026. Child branch: `feature/mobile-assessment-two-modes-2026-10`.
Base: Mobile V1.1 #35, `771868a1f2694b6f58d6584fee993362d68b1942`.
Draft PR must target `feature/mobile-v1-1-private-android-runtime-2026-10`, never main. No merge authorised.

## Before and after

The read-only audit captured the functioning production Flask UI in Chromium at 390 px before source edits. It confirmed the Pause/Resume feature promotion, competing ordinary/pausable start forms, oversized palette, an active handwritten solution reveal after marking attempted, and inaccurate synthetic-review text for ordinary imported packages. Local Android SDK/emulator is absent, so these baseline captures are browser evidence, not installed-app evidence.

The home now leads with exactly two cards, **CBT Based Test** and **Handwritten Test**, followed by real signed-POST paused attempts only when present, Recent Tests and Create / Import Test. Reports, templates and academic timelines remain available as secondary tools.

## Routes and policies

| Route | Behaviour |
| --- | --- |
| `/assessments` | Read-only two-mode overview; actual paused kind, question and frozen time |
| `/assessments/tests?assessment_mode=cbt` | Same canonical package library, CBT context; no attempt created |
| `/assessments/tests?assessment_mode=handwritten` | Same library, authored subjective import eligibility and useful unavailable reasons |
| `/assessments/tests/<id>?assessment_mode=...` | One context-specific preflight and Start; existing attempts retain their kind |
| POST `/assessments/tests/<id>/start` | Validates mode, instructions and paper acknowledgement/admission before starting |
| `/assessments/extended/sessions/<id>` | Existing revision-checked active-time practice player; contextual palette Pause Test / Resume Test |
| `/assessments/sessions/<id>` | Existing legacy runner, or canonical redirect for an already extended attempt |

Only `cbt` and `handwritten` are accepted as navigation values. New personal CBT practice uses existing extended execution by default. Fixed-time exams retain the legacy runner, timing and scoring policy. Unsupported/unapproved handwritten imports fail before creating an orphan attempt. No GET card or preflight starts the clock. No schema migration, history reset or attempt-kind conversion was introduced.

Pause atomically saves the response, review flag and current position using existing SQLite transactions, revision checks and receipt identities. Paper palette navigation and attempted acknowledgements persist the current ordinal. Save & Next and submission preserve visible CBT work; next destinations derive from immutable submitted question ordinals so an identical lost-response retry replays the receipt. Failed acknowledgements retain controls, input and truthful retry status. Native stale multipart-fill errors retain their actual visible inputs too.

Handwritten solutions are blocked in both mutation handling and authorized-guide projection while the persisted solving session remains active, including previously revealed legacy metadata. Finish Solving or confirmed timeout opens authored step/per-question self-check. Existing increments, prerequisite/alternative-method validation, versioned correction history and private authority boundaries remain unchanged. Production pages describe imported, independently unverified self-review provenance; synthetic fixture wording is confined to the development preview.

CBT practice feedback reuses the existing deterministic scoring function without creating official evaluation/topic evidence. Pending subjective/custom marks are explicitly ungraded. Fixed-time official evaluation is untouched. UC100N Coding Helper, Operations Map and Colab remain available through the existing policy/provider boundary; the helper's visible-task context rejects paused, completed, non-current and handwritten questions. This change does not enable online AI in Android or add a provider.

## Verification and delivery

New route/service regressions cover mode input, approved/ineligible imports, zero GET writes, fixed-time policy, key gating, restart position, real paused POST Resume, private CBT scoring, atomic submission, multipart fills, stale input, receipt replay and UC100N tools. Browser acceptance exercises both modes in dark/light at 320,360,390,430,768,1366 and 844×390 landscape, including actual imported-package start, pause/reopen/resume, review and no overflow. A separate browser check confirms helper forms cannot be intercepted as assessment mutations.

The independent review identified and reproduced three P2 defects (next replay, stale fill retention and UC100N tools); each received regression coverage and a fix. The full test log and exact-source CI records govern final certification. No external-provider Tutor scenarios are claimed by this assessment task.

Smart Verification files are absent from the mandated Mobile #35 base. Unrelated main/parallel work was not merged merely to obtain them. Focused tests run first, then the existing complete Python/browser and frontend contracts without deselections or relaxed gates.

The existing Android workflow now also runs for this stacked PR target. It retains independent APK/JVM, native Ubuntu/Windows full regression and API31 offline emulator jobs. Instrumentation now checks two mode choices and a separate authored handwritten attempt paused at question 2 across real force-stop/package replacement, alongside existing CBT, review and data-preservation tests. Synthetic assets remain solely in the instrumentation APK. Browser screenshots are uploaded with regression artifacts; native screenshots and the exact tested APK are uploaded only by the actual emulator job.

Download the installable debug APK from the successful current-head emulator artifact, following `../v1_1/INSTALLATION.md`. A build artifact alone does not certify installed lifecycle checks. Physical-phone certification and additional Android API levels are not claimed. Keep this PR draft/unmerged until owner approval.
