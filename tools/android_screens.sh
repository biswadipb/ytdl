#!/usr/bin/env bash
# Takes real screenshots of the Android app in an emulator. Run by CI inside the emulator runner.
set -euo pipefail
OUT="${1:-docs/screenshots}"
APK="android/app/build/outputs/apk/debug/app-universal-debug.apk"
PKG=dev.ytdl.app
mkdir -p "$OUT"

shot() { adb exec-out screencap -p > "$OUT/android-$1.png"; echo "saved $1"; }
swipe_up() { adb shell input swipe 540 1700 540 500 500; sleep 1; }

adb install -r "$APK"
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true
# A tidy status bar: fixed clock, full battery and signal, no notification icons.
adb shell settings put global sysui_demo_allowed 1
adb shell am broadcast -a com.android.systemui.demo -e command enter >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 1000 >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command network -e wifi show -e level 4 >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false >/dev/null

screens() {   # $1 = suffix for the file names
  adb shell am force-stop $PKG
  # Sharing a link opens the first-time "download shared links automatically?" card.
  adb shell am start -a android.intent.action.SEND -t text/plain \
    --es android.intent.extra.TEXT "Me at the zoo https://youtu.be/jNQXAC9IVRw" -n $PKG/.ShareActivity
  sleep 45                       # the first launch unpacks the download engine
  shot "home-$1"
  for i in 1 2 3 4; do swipe_up; shot "scroll$i-$1"; done
}

adb shell cmd uimode night no
screens light
adb shell cmd uimode night yes
screens dark
