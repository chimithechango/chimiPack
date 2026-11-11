# chimiPack

[PORTION OF THIS PROGRAM INCLUDING THE README WAS CREATED WITH THE ASSISTANCE OF ARTIFICIAL INTELLIGENCE]

A chimi tool that packs any HTML page (and the JS, CSS, images, sounds and fonts it uses) into:

| Output | What you get |
|---|---|
| **Windows `.exe`** | One file, no install, no browser. Your page runs in its own Electron window and works offline. |
| **Android `.apk`** | A signed app, ready to install on your phone. |
| **iPhone/iPad `.ipa`** | A real iOS app (iOS 14 or newer), built without a Mac. Install it with a sideloading tool. |
| **Linux `.deb`** | A package for Ubuntu, Mint, Debian or Pop!_OS that adds the app to the menu. |
| **Linux `.run`** | A portable file that works on any distro. |

## Start it

Double-click **`Start chimiPack.bat`**. You need Python 3.9 or newer, and nothing else.
chimiPack opens in its own Electron window. On the very first start it downloads
Electron 44.9.3 once (about 110 MB, checked against the official checksums) into
`%USERPROFILE%\.chimipack\electron`. After that it works offline.

1. Drop an HTML file, a folder or a `.zip` onto the window (or use **Choose file**/**Choose folder**).
2. Set the name, App ID and version. Click the icon to use your own image; otherwise a solid-color
   icon with the app's first letter is generated.
3. Tick the platforms you want and click **Build** (or press Ctrl+Enter).

**Settings** (the gear in the top-right corner, or Ctrl+,) has the theme (System, Light, Dark), the
output folder (default `Documents\chimiPack Builds`), an option to open that folder after each build,
your publisher name, the color for generated icons, the build log, and your Android signing key.

## Installing the results

- **Windows:** just run the `.exe`.
- **Android:** copy the `.apk` to your phone, open it, and allow "Install unknown apps".
  To update an app, keep the same App ID and use a higher version number.
- **iPhone/iPad:** Apple only lets signed apps run. Install [Sideloadly](https://sideloadly.io) (or
  AltStore) on your PC, plug in your iPhone, drag the `.ipa` in and sign in with your Apple ID. It signs
  the app for your phone. On the phone, go to Settings → General → VPN & Device Management and trust
  your Apple ID. On iOS 16 or newer, also turn on Settings → Privacy & Security → Developer Mode.
  With a free Apple ID, apps stop opening after 7 days until you reinstall them, and you can have at most
  3 at once. A paid Apple Developer account ($99/year) removes both limits.
- **Linux .deb:** `sudo apt install ./yourapp.deb`
- **Linux .run:** `chmod +x YourApp.run && ./YourApp.run` (add `--install` to put it in the app menu)

## How it works

- Apps don't load your files as plain `file://` pages. This means `fetch()`, ES modules,
  WebAssembly, `localStorage` and IndexedDB work as they do on a real website, and saved data
  persists between launches.
- **Windows:** each `.exe` is a small launcher, compiled with the C# compiler that comes with
  Windows, with the Electron runtime and your files appended to it. The first time you open
  it, Electron is unpacked into `%LOCALAPPDATA%\chimiPack` (a few seconds, shared by all
  chimiPack apps). After that it starts in under a second. Your page loads from a private
  `app://` address inside Electron, so no web server and no browser are involved.
  Keys: F11 toggles fullscreen, F5 reloads, Ctrl +/- zooms, Ctrl+Shift+I opens dev tools.
- **Android:** a small WebView launcher (`android-launcher/`, already compiled into
  `chimipack/data/launcher.dex`) is packaged together with your files. The APK is signed with
  APK Signature Scheme v2 using a key created on first use and stored in
  `%USERPROFILE%\.chimipack\android-signing-key.json`.
  **Back this key up** (Settings → Show file). Android only accepts updates signed with the same key.
- **Upgrading from HTML2App** (chimiPack's earlier name) is automatic: on first start, chimiPack moves
  `%USERPROFILE%\.html2app` (signing key, settings, Electron download) to `.chimipack`. Apps you
  rebuild keep their saved data: Windows apps move it from `%APPDATA%\HTML2App\<App ID>` and Linux
  apps from `~/.local/share/html2app/<App ID>`. Android and iPhone apps keep theirs as long as the
  App ID stays the same.
- **iOS:** a small launcher (`ios-launcher/main.m`) shows your page in WKWebView, iOS's built-in
  web engine, and serves your files from a private `app://` origin. `alert()`, `confirm()` and
  `prompt()` work, and links to other sites open in Safari. It's written so it needs no Apple SDK, and
  was cross-compiled on Windows with LLVM (`ios-launcher/build_ios_launcher.py`) into
  `chimipack/data/ios-launcher`. Every `.ipa` reuses that one binary.
- **Linux:** the app opens in an app window of Chrome, Chromium, Edge or Brave, falling back to
  Firefox or the default browser. It uses `python3` (installed on almost every distro) as its tiny local server.

## Limits

- Online content (CDN scripts, APIs) still needs an internet connection.
- Icons must be PNG, JPG, ICO, BMP or GIF. SVG icons aren't supported.
- Windows `.exe` builds must be made on Windows. The other outputs can be built anywhere.
- Each `.exe` is about 140 MB because the Electron runtime is bundled inside.
- The Linux apps still open in an installed browser's app window. Only the Windows output uses Electron.
