# ytdl

Download YouTube videos to your own device. Everything runs locally: no accounts,
no web service. Saved files play offline.

| Platform | App | Folder |
|---|---|---|
| Mac | `ytdl.app` window | `desktop/` |
| Windows | `ytdl.exe` window | `desktop/` |
| Android | `ytdl-android.apk` | `android/` |

Only download videos you have the right to save. YouTube's Terms of Service restrict downloading without permission.

## Install (no coding needed)

Open the **Releases** page of this repo and download the file for your device.
(The repo is private, so sign in to GitHub first.)

### Mac
1. Download `ytdl-mac-apple-silicon.zip` (M1/M2/M3/M4 Macs) or `ytdl-mac-intel.zip` (older Intel Macs).
   Not sure? Apple menu → About This Mac: "Chip: Apple…" means Apple silicon.
2. Double-click the zip, then drag **ytdl** into Applications.
3. First launch only: the app is not signed by Apple, so macOS blocks it.
   Right-click **ytdl** → **Open** → **Open**. If macOS still refuses, run this once in Terminal:
   ```bash
   xattr -dr com.apple.quarantine /Applications/ytdl.app
   ```

### Windows
1. Download `ytdl-windows.exe` and double-click it.
2. If "Windows protected your PC" appears: **More info** → **Run anyway**
   (the app is not code-signed).

### Android
1. On your phone, open the Releases page and download `ytdl-android.apk`.
2. Open the file. Android asks you to allow installs from your browser or Files app: allow it, then tap **Install**.
   Needs Android 10 or newer.
3. Tip: in the YouTube app tap **Share → ytdl** to drop the link straight in.

## Using it

Paste one or more links, choose a quality (or audio-only mp3), tap **Download**.
Files go to `Downloads/ytdl` on every platform.

If downloads suddenly fail, YouTube changed something. On Android tap **Update engine**.
On desktop, install the newest release (or `pip install -U yt-dlp` when running from source).

## Command line (Mac / Windows)

```bash
cd desktop
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                      # opens the window
python main.py URL -q 720 --audio   # command-line mode (see --help)
```

## Building the apps yourself

Releases are built by GitHub Actions (`.github/workflows/build.yml`) when you push a tag:

```bash
git tag v1.0.1 && git push origin v1.0.1
```

Mac and Windows apps must be built on those systems, which is why CI does it.
Local Android build: open `android/` in Android Studio, or `cd android && ./gradlew :app:assembleDebug`.
The APK is debug-signed so it installs directly.

## How it works

Desktop apps wrap [yt-dlp](https://github.com/yt-dlp/yt-dlp) with a tkinter window and a bundled ffmpeg.
The Android app uses [youtubedl-android](https://github.com/yausername/youtubedl-android), which bundles yt-dlp and ffmpeg.
