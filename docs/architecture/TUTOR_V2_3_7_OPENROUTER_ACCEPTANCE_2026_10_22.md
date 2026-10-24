# ANVAYA Tutor V2.3.7: first OpenRouter live acceptance

Date: 22 October 2026. PR #32 only, never main.

The owner saved `ANVAYA_TUTOR_LIVE_OPENROUTER_KEY` as a GitHub Actions repository secret. The trusted same-repository owner-only PR job uses the OpenAI-compatible endpoint `https://openrouter.ai/api/v1/chat/completions`, and pins `openai/gpt-oss-120b:free`. This is a different model from the Gemini 3.8 Flash tests. The runner selects **B, C, D, E, F, I, K**, the seven unresolved cases; the earlier genuine Gemini evidence for A, G, H, J remains independent and unchanged.

Each case starts actual Flask, Chromium at 1366px, existing Tutor teaching services, a fresh disposable SQLite course, and an actual HTTP model response. The suite checks visible teaching, persisted state, browser errors, and hashes of every protected non-Tutor table, then captures screenshots, per-step JSON, and JUnit.

The requested model is marked *free*, but provider availability and rate limits are not guaranteed. The suite caps all model attempts at **24** per GitHub run, paces requests to at least eight seconds apart, retries temporary 503 at most once, and circuits off future API calls after 429/402. Failed calls may count toward free quota. It does not send private source documents, installed databases, or personal academic records. Secrets are injected only into the presence check and actual real-model pytest step and never saved to artifacts.

For a given scenario: PASS means visible response and SQLite state satisfy its acceptance contract. FAIL means it was observed breaking a teaching or verification contract. BLOCKED means provider access/availability/quota prevented certification. A green simulated-provider test is not real provider certification. Review the reports and actual model output before any merge decision. This workflow replaces the automatic Gemini job (Gemini source and historical reports are preserved) to avoid further consumption of the currently exhausted Gemini free quota.

The existing full Tutor Ubuntu/Windows and all other ANVAYA mandatory checks continue to run independently. No merge into main until real A–K, exact-head native jobs and owner data safeguards satisfy agreed release criteria.
