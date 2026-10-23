# Android-local implementation plan

Primary specification: owner's 22 October 2026 Mobile V1.1 master prompt.
Baseline main b0f650c3f30e4c49201c2f7c2a0d7add41b34174; Mobile #34
99fbaeeaf9a400ff6eb0f98fa6132e0baa6ef47c; Tutor #32
 afc19763f4835687899ab0081084e715b54b2f24 (separate, not imported).

1. Package existing Python/Flask services with Chaquopy 16.1, Python 3.11,
   AGP 8.9.1, Gradle 8.11.1, Java 17. Include armv7/arm64/x86_64;
   Android min 24, target 35. Minimal native Java Activity/WebView avoids
   additional UI dependencies. MIT runtime; official compatibility documented
   at https://chaquo.com/chaquopy/doc/16.1/android.html .
2. Before UI polish, test local app initialization, production SQLite migrations,
   authenticated random-port transport, real saved Notes/restart, and route
   rendering. Runtime root is Android filesDir, never bundled source directory.
   Use 256-bit per-process HttpOnly cookie, exact Host/Origin, no CORS,
   deny unauthenticated static/API requests. No JS bridge or remote navigation.
3. Bundle only production Python source, SQL migrations, templates/static and
   explicit academic seed catalogue; no database, vault, secret, tests or logs.
   Omit optional desktop retrieval/model/native PDF rendering dependencies.
   Preserve route/service owners, no duplicate mobile academic calculation.
4. Build/install APK early; then emulator launch, saved action, force-stop,
   reopen, offline checks. Add screenshot/lifecycle instrumentation and native
   Ubuntu/Windows regressions in CI. Diagnose inherited failures from artifacts.
5. Add Storage Access Framework file selection and download/backup affordances
   with validation. Document unsupported native features and encryption status.
6. Commit focused increments; push dedicated branch, open stacked draft PR into
   Mobile V1. Keep main and Tutor untouched. Record counts and actual device
   evidence; pending/blocked gates never count as passes.

Review focus: local port access by other apps; cross-origin WebView requests;
process death with SQLite journals; insecure backup export; archive traversal;
32-bit phone compatibility; optional Python native dependencies.

Execution: inline as authorized by owner's implementation instruction.
