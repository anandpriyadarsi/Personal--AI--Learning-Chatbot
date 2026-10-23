#!/usr/bin/env bash
set -euo pipefail
mkdir -p android-evidence
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb install -r android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell svc wifi disable
adb shell svc data disable
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testCreateOfflineNote in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/create-note.log
python -c "from pathlib import Path;s=Path('android-evidence/create-note.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
adb shell am force-stop in.anvaya.privateapp
# Same-key, same-version package replacement must retain the saved workspace.
adb install -r android/app/build/outputs/apk/debug/app-debug.apk | tee android-evidence/update-install.log
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testNoteAfterForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/reopen-note.log
python -c "from pathlib import Path;s=Path('android-evidence/reopen-note.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
adb shell getprop ro.build.version.release > android-evidence/android-version.txt
adb shell getprop ro.product.cpu.abi > android-evidence/abi.txt
for name in android-today android-note-saved android--learning android--agent android--assessments android--library android--mobile-settings android--mobile-device android-note-after-force-stop android-sqlite-task-saved android-sqlite-task-after-force-stop android-active-lesson android-learning-mistake android-library-reader android-assessment-paused android-paper-step-review android-assessment-after-force-stop android-assessment-resumed android-paper-review-after-force-stop android-notes-landscape android-conversion-capability; do
  adb exec-out run-as in.anvaya.privateapp cat files/evidence/"$name".png > android-evidence/"$name".png
done

# Deliver precisely the APK which passed the installed-app checks above.
cp android/app/build/outputs/apk/debug/app-debug.apk android-evidence/ANVAYA_Mobile_V1_1_TEST.apk
sha256sum android-evidence/ANVAYA_Mobile_V1_1_TEST.apk > android-evidence/TESTED_APK_SHA256.txt
git rev-parse HEAD HEAD^{tree} > android-evidence/source.txt
