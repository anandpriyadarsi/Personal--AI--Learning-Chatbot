# Validation and acceptance evidence

All browser captures are genuine Chromium rendering of the running Flask app.
All stores and uploads are disposable synthetic fixtures. Android viewport
simulation is not physical Android testing. No real provider calls or API charges
occur in mobile validation. Tutor transcript tests use a labelled deterministic
provider plus real HTTP/SQLite persistence, not an LLM quality certificate.

## Reproduce

```
python -m pip install -r requirements-mobile.txt
python -m playwright install chromium
ANVAYA_BROWSER_TESTS=1 python -m pytest -q
node --test tests/js/*.test.cjs
```

On Windows PowerShell, use `$env:ANVAYA_BROWSER_TESTS='1'` before the pytest command.
`ANVAYA_MOBILE_ARTIFACTS` selects the synthetic screenshot directory. Mobile CI
runs the same contracts natively on Ubuntu and Windows and uploads JUnit,
source commit/tree identifiers, full-page captures and viewport captures.
No GitHub Actions provider secrets are consumed.

## Acceptance registry

Final exact-head CI results live in the draft PR checks and the
**Mobile V1 private PWA acceptance** artifacts. Pending runs are not passes.
The initial full-suite run exposed nine failures and was not accepted; the
corrections below preserve the original responsive/academic assertions.

| Requirement | Evidence / status |
| --- | --- |
| Private headers, loopback, DNS rebinding and cross-site writes | PASS: 8 HTTP boundary tests; cloud gate includes configured keys and missing acknowledgement |
| Today / Learn / Tutor / Practice / Library / Notes / Planning / Analysis | PASS: actual routes with synthetic owners; responsive matrix at 320/360/390/412/430, 768/1366 and 844×390 landscape; final source is rerun by CI |
| Touch navigation | PASS: real Chromium touch events and active destination checks; explicit accessible workspace labels disambiguate lesson links |
| Light/dark and readable lesson text | PASS: persisted theme, screenshot inspection and computed text/background checks; fixed legacy hardcoded dark colors |
| Phone keyboard | PASS for editable focus/reduced-height simulation retaining typed input; BLOCKED for physical Android keyboard/IME certification |
| Learning provenance / navigation / first concept | PASS: source identity/navigation plus original V1.3/V1.4/V2.3 regression assertions; 360/390 first-concept checks pass unchanged after trimming shell spacing |
| Tutor continuation | PASS: explicit synthetic exchange persists two turns in SQLite; reopen/new tab/refresh do not call provider again. Provider is deterministic, not live AI |
| Assessment timer / pause / resume | PASS: production extended routes at 320/390/430/844, saved response and 10-hour paused clock recovery; legacy runner and subjective regression suites included |
| Paper self-evaluation | PASS: production marking guide, step marks and persisted 3.0-mark self-review; no official grade/mastery claim |
| Library source identity | PASS: search → resource r1 → source d1 in actual reader |
| Notes editor | PASS: strict-CSP template selection, bold formatting, local image preview/insertion, save and durable reopen; extracted scripts preserve original behavior |
| Offline / reconnect | PASS: actual host stopped and restarted on the same port; generic fallback, failed mutation, no queued replay and safe recovery |
| Cache privacy | PASS: exactly five reviewed generic paths; no pages, APIs, query-string variants or mutations added |
| Worker updates | PASS: changed worker installs/waits beside active worker while page sentinel remains; no forced reload/activation |
| Browser outbound network | PASS: matrix blocks and records any nonlocal request; no third-party request observed |
| PWA metadata / eligibility | PASS: Chromium CDP reports no manifest or installability errors; local 192/512 icons and standalone manifest. BLOCKED: actual Android launcher installation/splash acceptance |
| Frontend worker / existing JS | PASS: 29 Node tests, including cache namespace, forbidden paths, offline navigation and mutation noninterception |
| Python regression | Full suite rerun after fixes; exact results in PR/CI. Exactly four unavailable private IKS fixture tests may skip; they remain BLOCKED rather than passed |
| Native Ubuntu / Windows | CI workflow implemented with zero-skip focused gate; final run results and artifacts linked from PR. A queued job is BLOCKED/pending |
| Existing installed records/backups | No real stores opened in cloud. No new migration/schema/academic owner. Existing backup-first normal startup preserved; installed-device restoration certification remains BLOCKED without that device |
| Authenticated encrypted phone-to-host access | BLOCKED: no validated private gateway provisioned; private prototype deliberately accepts loopback peers only |
| Standalone APK | BLOCKED: no embedded runtime/package/device certification. No APK built/distributed and no Play publication |

## Regression corrections and review

- New generic wrapping initially masked the source-reader stylesheet's ownership.
  Narrowed it so the original delayed-stylesheet overflow assertion stays intact.
- Large shell/reference controls pushed the first concept below its existing
  reading budget. Made the toolbar horizontally scrollable internally and
  trimmed chrome spacing, preserving text and touch-button height.
- Global Learn navigation collided with lesson-local Learn. Accessible names now
  identify workspace destinations; visible short labels remain unchanged.
- Worker-proxied POSTs bypassed an existing Chromium offline simulation. The
  minimal worker no longer intercepts mutations; existing save/error logic owns
  acknowledgement and retry. No background replay exists.
- `no-referrer` caused native forms to send Origin:null. `same-origin` keeps
  strict origin validation and suppresses external referrer transmission.
- Independent review reproduced two legacy inline scripts blocked by the CSP.
  Moved the unchanged code into local assets and tested actual editor behavior.
  Existing source tests now inspect the referenced asset as well as its template;
  none of their media/removal assertions were deleted.

The independent reviewer ran the eight HTTP contracts and reproduced the Notes
regression in Chromium. The author verified the fix with the new editor test;
no second independent review or real-device certification is claimed.

## Screenshots

The checked-in `screenshots/` directory contains viewport captures. Full-page
versions and additional sizes are CI artifacts. Captions identify synthetic
fixtures and do not imply the owner's private records were copied. Long source
notes, reference chips and self-review rubrics remain in the actual UI.
