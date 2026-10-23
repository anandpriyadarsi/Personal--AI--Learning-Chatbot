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
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testNoteAfterForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/reopen-note.log
python -c "from pathlib import Path;s=Path('android-evidence/reopen-note.log').read_text();assert 'OK (1 test)' in s and not any(v in s for v in ('FAILURES','INSTRUMENTATION_FAILED','shortMsg='))"
adb shell getprop ro.build.version.release > android-evidence/android-version.txt
adb shell getprop ro.product.cpu.abi > android-evidence/abi.txt
for name in android-today android-note-saved android--learning android--agent android--assessments android--library android--mobile-settings android--mobile-device android-note-after-force-stop android-sqlite-task-saved android-sqlite-task-after-force-stop; do
  adb exec-out run-as in.anvaya.privateapp cat files/evidence/"$name".png > android-evidence/"$name".png
done
