# Install the private Android test app

This is a debug-signed test APK, not a production release or a Play Store app.
It contains embedded Python/Flask, SQLite, templates and local assets. It needs
no companion computer, Python installation, hosting account or Google login.
Android 12 is a primary target; minimum Android 7 (API24), target API35.
ABIs: armeabi-v7a, arm64-v8a and x86_64. Owner-device acceptance is still required.

## From your Android phone

1. Download `ANVAYA_Mobile_V1_1_TEST.apk` from the supplied attachment. Alternatively
   sign into GitHub in your phone browser, open PR35 → Checks → Mobile V1.1
   standalone Android → successful `android` job/run → Artifacts →
   `anvaya-android-test-<commit>`. Download/extract its ZIP in Files and tap the APK.
2. Android may ask permission to install from the browser/ChatGPT/Files app. Allow
   that source for this installation, then tap Install. No developer mode,
   USB debugging, laptop or Termux is required.
3. Open ANVAYA. A fresh installation starts with no personal academic records.
4. My Notes → Create note works locally. App & privacy → Manage courses & backups
   provides local PDF selection, course labels and private workspace backups.
5. Register a PDF to obtain its canonical source ID. An authored Learning package
   must reference that ID and the exact PDF SHA256. Import the package through
   Learning Studio and review/publish it with existing validation. Source text is
   extracted locally; OCR and native PDF page rendering are not provided.
6. Verify your own phone: save a disposable note, close/force-stop/reopen, check
   it remains; disable Wi-Fi/mobile data and reopen it. These owner checks are
   distinct from automated cloud/emulator evidence.

## Save, pause and restore

Save Notes explicitly. Pause an assessment explicitly before closing if you want
its timer stopped. A running assessment retains the original engine's elapsed
wall-clock rules when backgrounded or killed. Closing is not an automatic pause.

Export via App & privacy → Manage courses & backups → Export private backup.
Android asks where to save the unencrypted ZIP using its document picker. Choose
a location you control. The app does not upload it or enable Android cloud backup.

Restore accepts the versioned ANVAYA Android archive only. It verifies hashes,
paths, size, SQLite integrity/foreign keys and production schema compatibility
on copies before staging. Save/pause current work, tap Save, then close ANVAYA,
confirm the native close dialog, and reopen the icon to apply it. The prior data
folder remains in app-private storage as a recovery copy. Current UI does not
provide a recovery-copy browser; do not delete a known-good external backup.

## Upgrade, erase and rollback

Keep the same signing key for in-place updates. Debug builds made on different
machines/runners can have different keys; Android may reject such an update.
Before uninstalling any build, export and retain a verified backup. Uninstalling
or clearing app storage erases all internal records and internal recovery copies.
Reinstall, then restore a compatible Android archive. Never assume a downgrade
can read a newer database schema.

Desktop SQLite IDs/schema are retained, but there is no automatic desktop sync
or general desktop-vault import wizard. Arbitrary desktop ZIPs are rejected;
portable desktop-to-phone migration needs a separately reviewed logical-root
bundle/import path. Existing Windows absolute resource paths are not guessed.
