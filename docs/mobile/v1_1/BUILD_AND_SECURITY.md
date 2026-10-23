# Reproduce and inspect the Android-local runtime

## Build

Java17 JDK, Python3.11 build interpreter, Android SDK35/build-tools35.0.0.
Chaquopy16.1.0, Android Gradle plugin8.9.1, Gradle8.11.1 wrapper with SHA256
verification. Runtime Python3.11 supports armv7/arm64/x86_64 and minimum API24.
Chaquopy is MIT licensed; dependency licensing remains with each dependency.

```sh
cd android
./gradlew assembleDebug assembleDebugAndroidTest testDebugUnitTest
# Windows: gradlew.bat with the same tasks
```

APK: `android/app/build/outputs/apk/debug/app-debug.apk`.
Native test APK: `android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk`.
Run the synthetic API31 emulator smoke with `bash scripts/android_emulator_acceptance.sh`
after booting an emulator in the same environment. It turns Wi-Fi/mobile data off,
saves via the real WebView Notes form, force-stops the package, reopens/checks the
record and captures actual Android screenshots. Normal ANVAYA screenshots and screen recordings are intentionally allowed at the
owner's request. Instrumentation must not clear FLAG_SECURE: it asserts that
screenshots are already permitted in the normal app. Screenshots can contain
sensitive learning records, so the owner should review them before sharing.

For a private release, generate/keep an owner-controlled Android signing keystore
outside this repository, configure a local Gradle signingConfig via environment
or private properties, and build `assembleRelease`. The current release task is
unsigned unless that private configuration is supplied. Never commit a keystore,
provider key, personal database, vault, APK with real records or signing password.

## Data and transport

Native Context.filesDir is canonicalized at the Java boundary because Android
can expose platform aliases. Arbitrary symlink roots are still rejected in
Python. `ANVAYA_ANDROID_DATA_ROOT` is set before legacy config import; data,
resources, backups, Notes JSON and dedicated Learning SQLite stay under that
private root. Existing owner/migration checks remain; no installed schema reset.
Ordinary desktop launches retain their prior paths.

The app binds only 127.0.0.1 on a dynamic OS-assigned port. Every route, API and
asset requires a new 256-bit capability cookie installed natively before the
first navigation. It is HttpOnly, SameSite=Strict, held for this process, never
put into a URL/DOM/intent/log. Requests enforce exact Host/Origin; writes require
Origin, and existing CSRF checks remain active. No CORS is enabled. Native
requests are serialized so backup/actions cannot race another native HTTP write.
The existing trusted WAL publisher exposes bounded committed RAM snapshots to
Library/Planning/Analysis; readers never attach to the live WAL index.

WebView allows only the exact local HTTP scheme/host/port. File/content URL
access, universal file access, popups, mixed content and WebView debugging are
disabled. There is no JavaScript bridge. External origins/subrequests are
blocked; CSP remains local. Local downloads stream through an authenticated
native request into a user-selected SAF document. Incoming intents never supply
backend roots, remote URLs, tokens or commands. Only the launcher Activity is
exported; it is singleTask. No exported service/provider is added.

INTERNET is the only Android permission, needed for the private loopback socket.
No broad storage, camera, microphone, notifications or account permission is
requested. Python DNS/connect/connect_ex reject non-loopback destinations in
this build. Cloud AI is disabled regardless of credentials. Online consent and
provider setup are deliberately unavailable in this increment. No provider or
personal-record upload occurs. Generic PWA service workers are disabled inside
the native runtime; offline work uses the actual local backend and data owners.

## Backup and remaining security limits

Android automatic backup is disabled. Exports are user initiated, unencrypted,
bounded versioned ZIPs with SHA256 per entry. This is integrity verification, not
an authenticity signature or encryption. App-private SQLite/JSON is not a claim
of encryption at rest. Android platform disk encryption/device lock is separate.

Archives reject traversal, symlinks, duplicate/undeclared entries and SQLite
sidecars. SQLite export uses online backup, not raw live database/WAL copies.
Staged restore validates production migrations on copies before replacing data.
The prior data directory is retained; migration backups remain backup-first.
Multi-store export is serialized against native HTTP writes, but is not claimed
to be a distributed transaction or a general desktop migration tool.

Release hardening, stable release signing, owner-device accessibility/IME,
low-memory/update certification, encrypted export and recovery-copy browsing
remain explicit future gates. This draft must not be merged as a full mobile
feature-parity certificate.

PDF draft conversion/edit/stage that launches a separate Python worker is
unavailable on Android and explicitly gated in the UI and POST routes (422).
Chaquopy provides an embedded interpreter, not a standalone Python executable.
Local PDF registration/text extraction, original-file downloads, authored
Learning package imports and published lessons still run on-device. Native
downloads retain the response's sanitized filename and MIME type for PDFs,
text briefs and backup ZIPs. The instrumented download check inspects the actual
SAF intent and cancels it; it does not certify a user's external storage provider.

## Primary compatibility references

- https://chaquo.com/chaquopy/doc/16.1/android.html
- https://chaquo.com/chaquopy/doc/16.1/versions.html
- https://github.com/chaquo/chaquopy/blob/master/LICENSE.txt
- https://developer.android.com/training/data-storage/app-specific
- https://developer.android.com/training/data-storage/shared/documents-files
- https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges
