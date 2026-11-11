"""Cross-compiles the iOS launcher (main.m) on Windows/Linux with LLVM - no Mac, no Apple SDK.

Usage:  python build_ios_launcher.py <path-to-llvm-bin>
Output: ../chimipack/data/ios-launcher (arm64 Mach-O, ad-hoc signed)

Linking uses hand-written text stubs (.tbd) that only name the system libraries and the few
symbols the launcher imports; the real ones are on every iPhone.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "chimipack", "data", "ios-launcher")
MIN_IOS = "14.0"

STUBS = {
    "usr/lib/libobjc.tbd": ("/usr/lib/libobjc.A.dylib", [
        "_objc_msgSend", "_objc_msgSendSuper2", "_objc_getClass", "_objc_allocateClassPair",
        "_objc_registerClassPair", "_class_addMethod", "_sel_registerName", "_objc_autoreleasePoolPush",
        "_objc_autoreleasePoolPop", "_objc_alloc", "_objc_alloc_init", "_objc_opt_new", "_objc_opt_class",
        "_objc_opt_respondsToSelector", "_objc_opt_isKindOfClass", "_objc_retain", "_objc_release",
        "_objc_autorelease", "__objc_empty_cache"], ["NSObject"]),
    "usr/lib/libSystem.tbd": ("/usr/lib/libSystem.B.dylib", [
        "dyld_stub_binder", "_strcmp", "_sscanf", "__NSConcreteStackBlock", "__NSConcreteGlobalBlock",
        "__Block_object_assign", "__Block_object_dispose", "__Block_copy", "__Block_release"], []),
    "Frameworks/CoreFoundation.framework/CoreFoundation.tbd": (
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
        ["___CFConstantStringClassReference"], []),
    "Frameworks/Foundation.framework/Foundation.tbd": (
        "/System/Library/Frameworks/Foundation.framework/Foundation", ["_NSLog"], []),
    "Frameworks/UIKit.framework/UIKit.tbd": (
        "/System/Library/Frameworks/UIKit.framework/UIKit", ["_UIApplicationMain"], []),
    "Frameworks/WebKit.framework/WebKit.tbd": (
        "/System/Library/Frameworks/WebKit.framework/WebKit", [], ["WKWebView"]),
}


def tbd(install_name, symbols, classes):
    lines = ["--- !tapi-tbd", "tbd-version: 4", "targets: [ arm64-ios ]", f"install-name: '{install_name}'",
             "current-version: 1", "compatibility-version: 1", "exports:", "  - targets: [ arm64-ios ]"]
    if symbols:
        lines.append("    symbols: [ " + ", ".join(f"'{s}'" for s in symbols) + " ]")
    if classes:
        lines.append("    objc-classes: [ " + ", ".join(classes) + " ]")
    lines.append("...")
    return "\n".join(lines) + "\n"


def main(llvm_bin):
    work = tempfile.mkdtemp(prefix="chimi_ios_")
    for rel, (name, syms, classes) in STUBS.items():
        p = os.path.join(work, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", newline="\n") as f:
            f.write(tbd(name, syms, classes))
    exe = ".exe" if os.name == "nt" else ""
    clang, lld = os.path.join(llvm_bin, "clang" + exe), os.path.join(llvm_bin, "lld" + exe)
    obj = os.path.join(work, "main.o")
    run([clang, "-c", "-x", "objective-c", "-target", f"arm64-apple-ios{MIN_IOS}", "-O2", "-fno-objc-arc",
         "-fblocks", "-fno-objc-msgsend-selector-stubs", "-nostdinc", "-Wall", "-Wno-objc-root-class",
         "-Wno-incomplete-implementation", "-Wno-objc-method-access",
         os.path.join(HERE, "main.m"), "-o", obj])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # Output by bare file name (run from the output folder): the ad-hoc signature's identifier is
    # the -o value, and a full path there would leak the build machine's folders and username.
    run([lld, "-flavor", "darwin", "-arch", "arm64", "-platform_version", "ios", MIN_IOS, "17.0",
         "-o", os.path.basename(OUT), obj, "-L", os.path.join(work, "usr", "lib"), "-lobjc", "-lSystem",
         "-F", os.path.join(work, "Frameworks"), "-framework", "UIKit", "-framework", "CoreFoundation",
         "-needed_framework", "Foundation", "-needed_framework", "WebKit", "-dead_strip", "-adhoc_codesign",
         "-S"], cwd=os.path.dirname(os.path.abspath(OUT)))  # -S: no debug info either
    print("Built", os.path.abspath(OUT), os.path.getsize(OUT), "bytes")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.stdout.strip() or r.stderr.strip():
        print((r.stdout + r.stderr).strip())
    if r.returncode:
        sys.exit(r.returncode)


if __name__ == "__main__":
    main(sys.argv[1])
