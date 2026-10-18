# Cross-platform acceptance

Published implementation source: f2e956ae8cf2aea55b77540300f66d5a06d00d6a. Its Git tree675d413864e0009f89c032a34050442add9603ff was independently matched to reviewed local product commit12fdef072ab95a8e5829320533ab354eed0009e8. The final evidence/report update is tracked separately; the PR head and each workflow artifact's source.json identify its exact tested SHA.

| Gate | Evidence |
|---|---|
| Dedicated Ubuntu/Windows UI + full regression | https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39129580894 |
| Existing full synthetic architecture matrix | https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39129580910 |
| Existing Assessment preservation matrix | https://github.com/anandpriyadarsi/Personal--AI--Learning-Chatbot/actions/runs/39129580916 |

At report preparation these hosted runs were still in progress; pending is not PASS. Final outcomes, counts and links are included in the downloadable acceptance-results.json and PR handoff. The dedicated focused browser step rejects any skipped case, and the full-suite step preserves complete JUnit/log evidence. No failing platform may be represented as green.

Local evidence: source/route compatibility run88 passed; extended UI/compatibility run170 passed; independent source/sanitizer run60 passed; protected browser14 passed; independent repair selection7 passed. The full local run passed 2501 tests with 4 explicit external Learning pilot fixture skips in 412.41 seconds (full.xml/full.log). These skips do not certify the missing external pilot material. Initial failed runs were retained separately when relevant to review closure, including the normal-motion drawer and order-dependent launcher fixture. Node syntax and git diff --check pass.

No Windows user setup or personal academic data is required. Hosted workflows install pinned dependencies and Chromium and use only disposable synthetic fixtures. Production deployment, data-authority certification and main merge remain outside this feature's acceptance.
