# Android navigation resource-loading improvement (candidate)

Source branch: `fix/android-navigation-asset-performance-2026-10-24`, stacked on the source/Assessment Android fix PR #43.

## Diagnosis

The old WebView explicitly set `LOAD_NO_CACHE` and the phone server sent
`Cache-Control: no-store` for *every* authenticated response. Each page
navigation therefore redownloaded the app's packaged CSS/JS/images.
The server also serialized static requests behind the same lock as academic
reads/writes and backed-up work, and performed retrieval-runtime cleanup even
for static resources that never touch the academic index.

## Change

- WebView `LOAD_DEFAULT`: allow HTTP caching only when server policy permits.
- For authenticated `GET`/`HEAD` requests to Flask's *packaged* `static`
  endpoint, send `Cache-Control: private, max-age=300` and retain ETag/last-modified
  support. This is process-scoped app code and contains no student records.
- Static requests bypass the academic request lock; they still receive all
  native capability-cookie, exact Host/Origin, and cross-site protections.
- Every other endpoint, error, download, academic page, and assessment/tutor
  operation retains `no-store` and the original request serialization/cleanup.
- No service worker, third-party network access, personal content caching,
  new data owner, schema migration, or API key exposure.

## Verification requirements

- Run `python -m pytest -q tests/test_android_navigation_performance.py` and
  existing `tests/test_android_runtime.py` and Android regressions.
- Verify both conditional 304 and authentication denial; check dynamic HTML,
  responses, uploads and backup exports still use `no-store`.
- Run the full native Ubuntu/Windows CI and installed Android API31 smoke before
  treating this as an accepted APK.
- On the owner's Android phone, compare median 5-run warm navigations across
  Home → Learning → Library → Assessments → Notes → Tutor → Home before/after.
  Repeat with offline network and after force-stop. Record milliseconds,
  visibly correct content, forms/notes saved, and memory/battery observations.
  No numeric speedup has been measured or claimed.

The existing PR #43 architecture Windows suite needs separate completion; a
green Android test is not equivalent to whole-repository acceptance.
