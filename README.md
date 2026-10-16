<p align="center"><img src="assets/logo.png" width="128" alt="ytdl logo"></p>

# ytdl

Download videos from **YouTube, Instagram, X/Twitter and Facebook** to your own device, as
video or audio-only. Everything runs locally: no accounts, no web service. Saved files play offline.

| Site | Status |
|---|---|
| YouTube | Works |
| Instagram (posts, reels) | Works; many posts need a login (see below) |
| X / Twitter | Works for posts that contain video |
| Facebook (videos, reels) | Works for public videos; others need a login |
| Threads | **Not supported yet.** The download engine has no Threads support, so links are tried but usually fail |

**Formats:** video as `mp4`, `mkv` or `webm`; audio only as `mp3`, `m4a`, `opus`, `wav` or `flac`.

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

Paste one or more links, pick a format (video or audio), pick a quality, tap **Download**.
Files go to `Downloads/ytdl` on every platform. Audio files get "(audio)" in their name so they never overwrite a video.

**Login-only posts (desktop):** Instagram, Facebook and some X posts refuse anonymous downloads.
Log in to the site in Chrome, Firefox, Safari, Edge or Brave, then choose that browser under
**Use login from** (CLI: `-b chrome`). Your browser data stays on your computer; on Mac you may see a
Keychain prompt. The Android app can't borrow a login, so it only handles public posts.

If downloads suddenly fail, YouTube changed something. On Android tap **Update engine**.
On desktop, install the newest release (or `pip install -U yt-dlp` when running from source).

## Command line (Mac / Windows)

```bash
cd desktop
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                      # opens the window
python main.py URL -F mp4 -q 720    # video
python main.py URL -F flac          # audio only
python main.py URL -b chrome        # use your browser login (see --help for more)
```

## Building the apps yourself

Releases are built by GitHub Actions (`.github/workflows/build.yml`) when you push a tag:

```bash
git tag v1.0.1 && git push origin v1.0.1
```

Mac and Windows apps must be built on those systems, which is why CI does it.
Local Android build: open `android/` in Android Studio, or `cd android && ./gradlew :app:assembleDebug`.
The APK is debug-signed so it installs directly.

## Logo

Master design: `assets/logo.svg`. To regenerate the PNG, `.ico` and `.icns` files:
`pip install pillow && python assets/make_icons.py`.

## How it works

Desktop apps wrap [yt-dlp](https://github.com/yt-dlp/yt-dlp) with a tkinter window and a bundled ffmpeg.
The Android app uses [youtubedl-android](https://github.com/yausername/youtubedl-android), which bundles yt-dlp and ffmpeg.
