# Tutor UI V3 audit and route contract

Baseline: integrated main + Android, 72a2ff2. Synthetic real Chromium screenshots at 360,390,768,1366 (four passing captures). The first 390px screen is consumed by the hero, four metrics and learning-journey panel; conversation starts below the fold. Home places Mentor ahead of session creation. Assistant messages repeat cards and support metadata. Provider failures return an empty composer and a fresh request ID.

## Retained contracts
- GET /agent: workspace.courses, tutor_topics, modes, source_policies, provider_configured, mentor, sessions. Read only; no LLM call.
- POST /agent/sessions: csrf_token; course_id, optional topic_id, mode, source_policy, title. Session settings remain immutable.
- GET /agent/sessions/<id>: persisted ordered turns with role/time/provenance/evidence; adaptive_state, session_goal, teaching_plan, persistent_student_model, optional memory candidates. No provider call.
- POST /agent/sessions/<id>/ask: csrf_token, request_id, question. Preserve server-side deduplication; retain validated draft and nonce after failure. No automatic retries or simulated streaming.
- Existing feedback and memory propose/accept/reject POSTs retain CSRF and explicit approval. No academic schema/reset or mastery/grade changes.
- Existing safe tutor_markdown + local assessment_math.js remain authority. Source links retain knowledge document IDs.

## Implemented design
Compact Tutor home with working mode starters and course/topic controls; recent conversations ahead of secondary Mentor. Session context stays compact; conversation precedes expandable metrics, learning journey and optional memory. Pending questions remain visible. Distinct student/Alex turns, collapsible source/model/feedback details and fixed auto-growing composer retain all five explicit-submit prompts. Native form semantics, server CSRF and request IDs remain authoritative. No academic text in browser storage. Themes use existing locally bundled tokens, no CDNs.

## Limits / privacy
Phone online AI is deliberately unavailable, not presented as configured. Required missing work: Android Keystore-backed key lifecycle, explicit consent/configuration/test/removal UI and narrowly restricted HTTPS transport with SSRF/redirect/TLS/context/rate-limit acceptance. Existing Android external-network and WebView origin blocks stay in place. No provider credentials used or shipped; no live-provider A–K claim. Desktop configured-provider operation remains unchanged.

Cloud fixtures are synthetic. Screenshots are permitted in production activity; native screenshot checks do not clear FLAG_SECURE. Physical owner-phone verification remains separate from Chromium/API31 emulator checks. Offline generative tutoring is not included.

## Review corrections
Inline and display maths now have bounded local horizontal scrolling. Successful asks navigate to the newest persisted turn; history GETs retain normal browser behavior. The sticky context uses the actual shared header height. Composer errors echo the safe server error next to the retained draft. Mentor advice opens after an explicit course request. Native keyboard evidence requires observed IME visibility; requesting keyboard display is not treated as proof.

## Phone-local source-index recovery
The installed test exposed a missing derived retrieval generation after restore. Android now has an explicit CSRF-protected local-index rebuild action using the production lexical builder with a read-only canonical DB and `acknowledge=False`. The Tutor service uses app-private `data/tutor_retrieval`; source freshness checks remain active. No new network allowance, credentials, schema reset, generated grading or silent ingestion. Native testing must rebuild the actual synthetic sources before checking a deterministic insufficient-evidence response.
