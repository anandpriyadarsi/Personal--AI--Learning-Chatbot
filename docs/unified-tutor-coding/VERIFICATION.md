# Verification evidence and limits

Development used Python 3.12, real Flask/SQLite owners and Chromium 134 through Playwright. Every fixture was synthetic and disposable. No production database or configured live provider was used.

| Local checkpoint | Result |
|---|---|
| Shared helper extraction and original Tutor characterization | 134 passed |
| Original focused Tutor/Assessment/Library/Learning Studio regressions, including Chromium | 238 passed |
| Combined focused acceptance including Assessment helper/timer browser regressions | 342 passed, zero skipped |
| New core/backend/notebook/browser checkpoint after source identity tests | 69 passed, zero skipped |
| Final context/provider-consent/UI refinements | 48 backend/browser cases passed; 44 backend/notebook cases passed |
| Node helper/copy/solution contracts | 6 passed, zero skipped |
| Changed Python compilation, changed JavaScript syntax, tracked diff whitespace | Passed |

The combined local run preceded the last small context/consent refinements, which were retested in the listed focused groups. **The final-head Windows/Linux workflow results and their artifacts are the authoritative integration evidence.** Do not treat a prior-head pass as a later-head pass. PR #72 links the actual checks and final source SHA. The web workflow preserves JUnit, screenshots, source identity and performance JSON and rejects skipped focused cases. Canonical CI is preserved without deselection or skip-CI markers.

Real browser journeys cover 320×568, 390×844, 768×1024, 1366×768, 1920×1080, 390×440 and 1366×440. Additional cases cover 200% page zoom, keyboard/Escape/focus, exact Unicode copy failure fallback, safe literal tracebacks, saved-task reopening, draft-preserving workspace toggles, failed-provider retry identity, notebook attachment download, fixed separate Colab link, rename and no page overflow/composer overlap. The loading acknowledgment measured about 0.7 ms in one local synthetic browser sample; CI saves its own measurement. This is not a real phone keyboard certification.

Backend tests cover typed field/byte limits, forged policy/token/history/owner fields, same-session ownership, request replay/conflicts, task CAS/archive, concurrent 429, source replacement during generation, provider identity changes, native Trash/indexing/placement/hash/generation/metadata/original availability, same-byte foreign sources, transaction rollback, feature-off/missing-schema reads, backup-first migration failure rollback and unchanged non-Tutor logical table dumps. A 200-turn/12,000-character code fixture checks bounded provider history.

Every authored notebook passes nbformat validation and deterministic public checks against trusted test-only reference attempts. Deliberately incorrect attempts fail those checks. Arbitrary file/network/script-looking student snippets are handled as inert text and never executed. Generated notebooks contain no hidden answer, credential, precomputed output or private source extraction.

Thirty local samples (200 synthetic turns and 12,000-character saved code, excluding provider time) measured p95 around **68 ms history rendering**, **7 ms task saving**, and **0.3 ms notebook serialization**. CI saves all raw samples in `coding-performance.json`; these results describe the synthetic local fixture, not every installed dataset or device.

**LIVE PROVIDER EDUCATIONAL QUALITY: NOT VERIFIED.** No already-configured live provider was available. Captured synthetic requests prove contracts and integration, not semantic teaching quality. The Colab contract verifies valid download plus manual upload instructions and the fixed HTTPS launch target; no authenticated Colab upload/runtime or output verification was performed. Authenticated runtime integration and notebook re-import are intentionally deferred. No Android APK/release or public deployment work was included.
