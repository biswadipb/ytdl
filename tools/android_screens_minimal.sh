#!/usr/bin/env bash
# Real screenshots of the minimal Android app in an emulator, with demo downloads. Run by CI.
set -euo pipefail
OUT="${1:-docs/screenshots}"
APK="minimal/android/app/build/outputs/apk/debug/app-universal-debug.apk"
PKG=dev.ytdl.minimal
mkdir -p "$OUT"
shot() { adb exec-out screencap -p > "$OUT/minimal-android-$1.png"; echo "saved $1"; }

adb install -r "$APK"
adb shell pm grant $PKG android.permission.POST_NOTIFICATIONS || true
adb shell settings put global sysui_demo_allowed 1
adb shell am broadcast -a com.android.systemui.demo -e command enter >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command clock -e hhmm 1000 >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command battery -e level 100 -e plugged false >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command network -e wifi show -e level 4 >/dev/null
adb shell am broadcast -a com.android.systemui.demo -e command notifications -e visible false >/dev/null

for theme in light dark; do
  [ "$theme" = light ] && adb shell cmd uimode night no || adb shell cmd uimode night yes
  adb shell am force-stop $PKG
  adb logcat -c
  adb shell am start -W -a android.intent.action.SEND -t text/plain --ez demo true \
    --es android.intent.extra.TEXT "'https://youtu.be/jNQXAC9IVRw'" -n $PKG/.MainActivity || true
  sleep 12
  echo "--- foreground ($theme):"
  adb shell dumpsys activity activities | grep -E "topResumedActivity" | head -2 || true
  adb logcat -d -v brief AndroidRuntime:E "*:S" | tail -30 || true
  shot "$theme"
done
