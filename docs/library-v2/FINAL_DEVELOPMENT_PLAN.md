# Library & Resources V2 final development

Owner specification: 19 October 2026 master work prompt in the execution session.
Base: c7998c113f9c7e36e00fcf5274bd79a60b486eb1. Initial PR #28 head: f6f685c8c433ec8e3ab526b699b2013074d26eb2.

## Boundaries

Only safe Library reads, existing Resources compatibility, scoped UI, tests and evidence. No migrations, imports, new write integrations, or PR #27/#29 implementation. Existing Resources POST contracts remain intact. Owner has authorized autonomous implementation and PR #28 merge after mandatory gates; no additional design approval is needed.

## Tasks

- [x] Fetch main and PRs 27/28/29, inspect checks/reviews/protection and confirm merge bases and isolation.
- [ ] Capture existing real-browser Library/Resources screenshots using disposable fixtures.
- [ ] Add bounded, literal, case-insensitive metadata search to LibraryQuery/repository/GET route/template; keep course/kind filters and search through pagination. Test Unicode, SQL metacharacters, private path exclusion, duplicates, oversize input and unchanged stores first.
- [ ] Improve Resources keyboard focus when opening the existing create form. Test real keyboard activation and native no-JS fallback; keep the existing create/status APIs.
- [ ] Resolve independently reproduced security findings within read-only Library scope.
- [ ] Verify final candidate with Library zero-skip, full regression, UI V2/browser/full and Assessment Ubuntu/Windows checks; disclose only four known unavailable-private-fixture skips. Inspect screenshots at desktop/mobile/tablet widths.
- [ ] Obtain independent whole-diff engineering/security and UX reviews on the final candidate; address critical/high findings.
- [ ] Re-fetch main/head, verify CI and mergeability, mark ready and merge only #28 with expected-head protection. Verify resulting main tree/parents, post-merge startup and read smoke tests.

## Review focus

Search never reads private paths or document bodies; wildcard characters are literal; all filters compose before pagination. No SQLite sidecar can be created by Library reads. Query errors remain safe and keyboard focus remains visible. Browser fixtures are synthetic and fingerprint checks protect stores.
