# Third-party software

ytdl is built on these projects. Their licenses apply to the parts of ytdl that include them.

| Component | Used for | License |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Talking to video sites and downloading | The Unlicense (public domain) |
| [youtubedl-android](https://github.com/yausername/youtubedl-android) | Runs yt-dlp and ffmpeg inside the Android app | GPL-3.0 |
| [FFmpeg](https://ffmpeg.org) | Merging, converting, clipping, tags and cover art. Mac and Windows apps use the static builds shipped by imageio-ffmpeg, which are built with `--enable-gpl`; the Android app uses the build inside youtubedl-android | GPL (the builds used here) |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Supplies the ffmpeg binary to the desktop apps | BSD-2-Clause |
| [Pillow](https://python-pillow.org) | Thumbnails in the desktop preview | MIT-CMU (HPND) |
| [PyInstaller](https://pyinstaller.org) | Packages the Mac and Windows apps | GPL-2.0 with an exception that allows packaged apps under any license |
| Tk / Tcl, Python | The desktop window | Tcl/Tk license, PSF license |
| AndroidX, Jetpack Compose, Material 3, Kotlin coroutines | The Android app | Apache-2.0 |

Because the apps include GPL-licensed components, ytdl is released under the GPL-3.0 (see [LICENSE](LICENSE)), and its complete source code is in this repository.
