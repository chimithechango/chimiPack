"""Builds an iOS .ipa (iPhone + iPad) without a Mac.

Contents: the pre-compiled universal launcher (data/ios-launcher, built from ios-launcher/main.m
with LLVM), a generated Info.plist, app icons and the web files under www/.

The .ipa is unsigned (the launcher carries only an ad-hoc signature). iPhones only run apps
signed with an Apple certificate, so it's installed with a sideloading tool such as Sideloadly
or AltStore, which signs it with the user's own Apple ID during install.
"""
import os
import plistlib
import re

from .ziputil import ZipWriter

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
EXECUTABLE = "chimiPack"
MIN_IOS = "14.0"

ORIENTATIONS = {
    "auto": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationLandscapeLeft",
             "UIInterfaceOrientationLandscapeRight"],
    "portrait": ["UIInterfaceOrientationPortrait"],
    "landscape": ["UIInterfaceOrientationLandscapeLeft", "UIInterfaceOrientationLandscapeRight"],
}
IPAD_ORIENTATIONS = {
    "auto": ORIENTATIONS["auto"] + ["UIInterfaceOrientationPortraitUpsideDown"],
    "portrait": ["UIInterfaceOrientationPortrait", "UIInterfaceOrientationPortraitUpsideDown"],
    "landscape": ORIENTATIONS["landscape"],
}
# file name -> icon size in pixels
ICON_FILES = {
    "AppIcon60x60@2x.png": 120, "AppIcon60x60@3x.png": 180,
    "AppIcon76x76@2x~ipad.png": 152, "AppIcon83.5x83.5@2x~ipad.png": 167,
}


def _short_version(v):
    nums = [str(int(x)) for x in re.findall(r"\d+", v)][:3]
    return ".".join(nums) if nums else "1.0"


def info_plist(cfg, has_icons):
    orient = cfg.get("orientation", "auto")
    p = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIdentifier": cfg["package"],
        "CFBundleName": cfg["name"][:15],
        "CFBundleDisplayName": cfg["name"],
        "CFBundlePackageType": "APPL",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleShortVersionString": _short_version(cfg["version"]),
        "CFBundleVersion": str(cfg.get("version_code", 1)),
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "MinimumOSVersion": MIN_IOS,
        "LSRequiresIPhoneOS": True,
        "UIDeviceFamily": [1, 2],
        "UIRequiredDeviceCapabilities": ["arm64"],
        "UILaunchScreen": {},                           # full-screen launch without a storyboard
        "UIRequiresFullScreen": True,
        "UIStatusBarHidden": bool(cfg.get("fullscreen")),
        "UIViewControllerBasedStatusBarAppearance": True,
        "UISupportedInterfaceOrientations": ORIENTATIONS.get(orient, ORIENTATIONS["auto"]),
        "UISupportedInterfaceOrientations~ipad": IPAD_ORIENTATIONS.get(orient, IPAD_ORIENTATIONS["auto"]),
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
        "ITSAppUsesNonExemptEncryption": False,
        "DTPlatformName": "iphoneos",
        "DTPlatformVersion": "17.0",
        "DTSDKName": "iphoneos17.0",
        "ChimiEntry": cfg["entry"],
        "ChimiFullscreen": bool(cfg.get("fullscreen")),
    }
    if has_icons:
        p["CFBundleIcons"] = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["AppIcon60x60"]}}
        p["CFBundleIcons~ipad"] = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["AppIcon60x60", "AppIcon76x76",
                                                                                 "AppIcon83.5x83.5"]}}
    return plistlib.dumps(p, fmt=plistlib.FMT_BINARY)


def bundle_folder_name(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return (s or "App") + ".app"


def build_ipa(cfg, files, icon_set, out_path, log=print):
    with open(os.path.join(DATA_DIR, "ios-launcher"), "rb") as f:
        launcher = f.read()
    app = "Payload/" + bundle_folder_name(cfg["name"]) + "/"
    has_icons = all(f"ios{s}" in icon_set for s in ICON_FILES.values())
    z = ZipWriter()
    z.add(app + EXECUTABLE, launcher, compress=True, align=0, mode=0o755)
    z.add(app + "Info.plist", info_plist(cfg, has_icons), align=0, mode=0o644)
    z.add(app + "PkgInfo", b"APPL????", align=0, mode=0o644)
    if has_icons:
        for fn, size in ICON_FILES.items():
            z.add(app + fn, icon_set[f"ios{size}"], align=0, mode=0o644)
        z.add("iTunesArtwork", icon_set["ios1024"], align=0, mode=0o644)
    for rel, full in sorted(files.items()):
        with open(full, "rb") as f:
            z.add(app + "www/" + rel, f.read(), align=0, mode=0o644)
    with open(out_path, "wb") as f:
        f.write(z.finish())
    return out_path
