#!/usr/bin/env bash
set -euo pipefail
mkdir -p android-evidence
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
adb install -r android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell svc wifi disable
adb shell svc data disable
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testCreateOfflineNote in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/create-note.log
! rg 'FAILURES|INSTRUMENTATION_FAILED|shortMsg=' android-evidence/create-note.log
rg 'OK \(1 test\)' android-evidence/create-note.log
adb shell am force-stop in.anvaya.privateapp
adb shell am instrument -w -r -e class in.anvaya.privateapp.OfflineSmokeTest\#testNoteAfterForceStop in.anvaya.privateapp.test/androidx.test.runner.AndroidJUnitRunner | tee android-evidence/reopen-note.log
! rg 'FAILURES|INSTRUMENTATION_FAILED|shortMsg=' android-evidence/reopen-note.log
rg 'OK \(1 test\)' android-evidence/reopen-note.log
adb shell getprop ro.build.version.release > android-evidence/android-version.txt
adb shell getprop ro.product.cpu.abi > android-evidence/abi.txt
for name in android-today android-note-saved android--learning android--agent android--assessments android--library android--mobile-settings android--mobile-device android-note-after-force-stop; do
  adb exec-out run-as in.anvaya.privateapp cat files/evidence/"$name".png > android-evidence/"$name".png
done
