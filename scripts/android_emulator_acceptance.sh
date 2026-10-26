#!/usr/bin/env bash
set -euo pipefail
mkdir -p android-evidence
git rev-parse HEAD HEAD^{tree} > android-evidence/source.txt
capture_exit_evidence() {
  result=$?
  trap - EXIT
  adb logcat -d -v threadtime > android-evidence/logcat.txt 2>&1 || true
  if [ "$result" -ne 0 ]; then
    adb exec-out screencap -p > android-evidence/failed-installed-viewport.png || true
    adb exec-out run-as in.anvaya.privateapp cat files/evidence/upload-picker-failure.png > android-evidence/upload-picker-failure.png 2>/dev/null || true
  fi
  exit "$result"
}
trap capture_exit_evidence EXIT
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb install -r android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell svc wifi disable
adb shell svc data disable
adb shell am instrument -w -r -e class in.anvaya.privateapp.UploadPickerTest in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/upload-picker.log
python -c "from pathlib import Path;s=Path('android-evidence/upload-picker.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
adb shell am force-stop in.anvaya.privateapp
adb shell settings put secure show_ime_with_hard_keyboard 1
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testCreateOfflineNote in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/create-note.log
python -c "from pathlib import Path;s=Path('android-evidence/create-note.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
adb shell am force-stop in.anvaya.privateapp
# Same-key, same-version package replacement must retain the saved workspace.
adb install -r android/app/build/outputs/apk/debug/app-debug.apk | tee android-evidence/update-install.log
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testNoteAfterForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/reopen-note.log
python -c "from pathlib import Path;s=Path('android-evidence/reopen-note.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
for method in actualExternalUidReadsContentUriWithReadOnlyGrantAndReturns providerCannotOpenPagesOrWriteAndShareCarriesGrant absentPlayerAndChooserCancellationPreserveNote; do
  adb shell am instrument -w -r -e class in.anvaya.privateapp.MediaHandoffTest\#"$method" in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee "android-evidence/media-$method.log"
  python -c "from pathlib import Path;s=Path('android-evidence/media-$method.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
done
adb shell am force-stop in.anvaya.privateapp
adb shell am instrument -w -r -e class in.anvaya.privateapp.MediaHandoffTest\#mediaRemainsAfterForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/media-after-force-stop.log
python -c "from pathlib import Path;s=Path('android-evidence/media-after-force-stop.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
# Smart Notes startup and universal provider contracts use the same installed APK.
for class in StartupSplashTest; do
  adb shell am instrument -w -r -e class "in.anvaya.privateapp.$class" in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee "android-evidence/smart-$class.log"
  python -c "from pathlib import Path;s=Path('android-evidence/smart-$class.log').read_text();assert 'OK (2 tests)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
done
adb shell am instrument -w -r -e class in.anvaya.privateapp.MediaHandoffTest\#documentAndImageAttachmentsHaveExactMimesAndReadOnlyAccess in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/universal-attachments.log
python -c "from pathlib import Path;s=Path('android-evidence/universal-attachments.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
# Exercise actual typed mini-note UI and a typed document via the production Intent.
for method in typedMiniNotesCrudAccordionAndActivityRestartPersistence typedDocumentUsesProductionGestureIntentAndExternalUidReadGrant; do
  adb shell am instrument -w -r -e class in.anvaya.privateapp.SmartNestedNotesTest\#"$method" in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee "android-evidence/smart-$method.log"
  python -c "from pathlib import Path;s=Path('android-evidence/smart-$method.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
done
adb shell am force-stop in.anvaya.privateapp
adb shell am instrument -w -r -e class in.anvaya.privateapp.SmartNestedNotesTest\#savedTypedNotesAndAttachmentsSurviveForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/smart-typed-force-stop.log
python -c "from pathlib import Path;s=Path('android-evidence/smart-typed-force-stop.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
# Original-document Library has a separate native renderer. Compilation alone
# cannot prove that its private content URI opens at the requested PDF page.
adb shell am instrument -w -r -e class in.anvaya.privateapp.NativePdfPageTest in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/native-pdf-page.log
python -c "from pathlib import Path;s=Path('android-evidence/native-pdf-page.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
for name in android-smart-mini-notes-expanded android-smart-mini-notes-after-activity-restart android-smart-typed-attachment-after-activity-restart android-smart-typed-after-force-stop; do
  adb exec-out run-as in.anvaya.privateapp cat files/evidence/"$name".png > android-evidence/"$name".png
done
adb shell getprop ro.build.version.release > android-evidence/android-version.txt
adb shell getprop ro.product.cpu.abi > android-evidence/abi.txt
for name in android-reader-full-view android-reader-full-view-landscape android-reader-expanded-figure android-library-renamed android-library-renamed-after-force-stop android-library-content-search android-library-saved-reference android-library-reference-after-force-stop android-tutor-conversation android-tutor-composer-keyboard android-tutor-after-force-stop android-today android-note-saved android--learning android--agent android--assessments android--library android--mobile-settings android--mobile-device android-note-after-force-stop android-sqlite-task-saved android-sqlite-task-after-force-stop android-active-lesson android-learning-mistake android-library-reader android-assessment-paused android-paper-step-review android-assessment-after-force-stop android-assessment-resumed android-paper-review-after-force-stop android-notes-landscape android-conversion-capability android-selection-cbt android-selection-handwritten android-handwritten-paused android-handwritten-after-force-stop android-handwritten-resumed; do
  adb exec-out run-as in.anvaya.privateapp cat files/evidence/"$name".png > android-evidence/"$name".png
done

# Deliver precisely the APK which passed the installed-app checks above.
source_short="$(git rev-parse --short=12 HEAD)"
verified_apk="android-evidence/ANVAYA-Unified-Android-V1.2.0-Debug-${source_short}.apk"
cp android/app/build/outputs/apk/debug/app-debug.apk "$verified_apk"
sha256sum "$verified_apk" > android-evidence/TESTED_APK_SHA256.txt
# Inspect the actual package installed above, not Gradle configuration alone.
adb shell dumpsys package in.anvaya.privateapp > android-evidence/installed-package.txt
adb shell settings get global wifi_on > android-evidence/wifi-on.txt
adb shell settings get global mobile_data > android-evidence/mobile-data.txt
aapt_tool="$(find "$ANDROID_HOME/build-tools" -type f -name aapt | sort -V | tail -1)"
test -n "$aapt_tool" && test -x "$aapt_tool"
"$aapt_tool" dump badging "$verified_apk" > android-evidence/apk-badging.txt
"$(dirname "$aapt_tool")/apksigner" verify --print-certs "$verified_apk" > android-evidence/apk-signature.txt
python - <<'PACKAGE_CHECK'
from pathlib import Path
import re
import ssl
import zipfile
report=Path('android-evidence/apk-badging.txt').read_text()
assert "name='in.anvaya.privateapp'" in report
assert "versionCode='16'" in report and "versionName='1.2.0-unified-debug'" in report
assert "sdkVersion:'24'" in report and "targetSdkVersion:'35'" in report
for abi in ('armeabi-v7a','arm64-v8a','x86_64'):
    assert abi in report, abi
apk=next(Path('android-evidence').glob('ANVAYA-Unified-Android-*.apk'))
with zipfile.ZipFile(apk) as archive:
    for name in archive.namelist():
        assert not name.lower().endswith(('.sqlite','.sqlite3','.db','.keystore','.jks','.key')), name
        assert '/androidTest/' not in name and 'workspace.zip' not in name, name
        if name.lower().endswith('.pem'):
            # Chaquopy ships public CA roots, not signing/owner credentials.
            # Permit only its exact path and certificate-only PEM contents.
            assert name == 'assets/chaquopy/cacert.pem', name
            raw = archive.read(name)
            assert len(raw) <= 2 * 1024 * 1024 and b'PRIVATE KEY' not in raw, name
            text = raw.decode('ascii')
            pattern = r'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+?-----END CERTIFICATE-----'
            certificates = re.findall(pattern, text)
            assert certificates, name
            for certificate in certificates:
                assert ssl.PEM_cert_to_DER_cert(certificate), name
            remainder = re.sub(pattern, '', text)
            assert all(not line.strip() or line.lstrip().startswith('#') for line in remainder.splitlines()), name
PACKAGE_CHECK
git rev-parse HEAD HEAD^{tree} > android-evidence/source.txt
