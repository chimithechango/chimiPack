"""Runs a full build for the selected targets."""
import os
import re
import time

from . import android, bundle, icons, ios, linux, windows

from . import migrate  # noqa: E402  (moves data from the old name before anything reads it)

HOME = migrate.NEW_HOME
KEY_PATH = os.path.join(HOME, "android-signing-key.json")
DEFAULT_OUTPUT = os.path.join(os.path.expanduser("~"), "Documents", "chimiPack Builds")

TARGETS = {
    "exe": "Windows (.exe)",
    "apk": "Android (.apk)",
    "ipa": "iPhone/iPad (.ipa)",
    "deb": "Linux (.deb package)",
    "run": "Linux (portable .run)",
}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower()) or "app"


def default_package(name):
    s = slug(name)
    if s[0].isdigit():
        s = "app" + s
    return "com.chimi." + s


def valid_package(p):
    return bool(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+", p or ""))


def safe_filename(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return s or "App"


def run_build(opts, log=print):
    t0 = time.time()
    name = (opts.get("name") or "My App").strip()
    package = (opts.get("package") or default_package(name)).strip()
    if not valid_package(package):
        raise ValueError("App ID must look like com.yourname.appname (letters, numbers, dots).")
    version = (opts.get("version") or "1.0.0").strip()
    targets = [t for t in opts.get("targets", []) if t in TARGETS]
    if not targets:
        raise ValueError("Pick at least one output type.")
    out_dir = opts.get("output_dir") or DEFAULT_OUTPUT
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        raise ValueError(f"Can't save to “{out_dir}”. Choose a different folder.")

    root, entry = opts["root"], opts["entry"]
    log(f"Collecting files from {root}")
    files = bundle.collect(root, entry, opts.get("mode", "folder"))
    total = sum(os.path.getsize(p) for p in files.values())
    log(f"  {len(files)} files, {total / 1048576:.1f} MB")

    log("Preparing icon...")
    icon_set = icons.make_icon_set(opts.get("icon") or None, name, log, color=opts.get("icon_color"))

    vc = opts.get("version_code")
    if not vc:
        nums = [int(x) for x in re.findall(r"\d+", version)][:3] + [0, 0, 0]
        vc = nums[0] * 10000 + nums[1] * 100 + nums[2] or 1
    cfg = {
        "name": name, "package": package, "version": version, "version_code": int(vc),
        "entry": entry, "publisher": opts.get("publisher", ""),
        "width": int(opts.get("width") or 1200), "height": int(opts.get("height") or 800),
        "fullscreen": bool(opts.get("fullscreen")), "orientation": opts.get("orientation", "auto"),
        "category": opts.get("category", "Utility"),
    }
    base = safe_filename(name)
    outputs, errors = [], []
    for t in targets:
        log(f"Building {TARGETS[t]}...")
        try:
            if t == "exe":
                p = windows.build_exe(cfg, files, icon_set, os.path.join(out_dir, base + ".exe"), log)
            elif t == "apk":
                p = android.build_apk(cfg, files, icon_set, os.path.join(out_dir, base + ".apk"), KEY_PATH, log)
            elif t == "ipa":
                p = ios.build_ipa(cfg, files, icon_set, os.path.join(out_dir, base + ".ipa"), log)
            elif t == "deb":
                fn = f"{linux.deb_name(package)}_{version}_all.deb"
                p = linux.build_deb(cfg, files, icon_set, os.path.join(out_dir, fn), log)
            else:
                p = linux.build_run(cfg, files, icon_set, os.path.join(out_dir, base + ".run"), log)
            outputs.append({"target": t, "label": TARGETS[t], "path": p, "size": os.path.getsize(p)})
            log(f"  done: {os.path.basename(p)}")
        except Exception as e:  # keep building the other targets
            errors.append({"target": t, "label": TARGETS[t], "error": str(e)})
            log(f"  FAILED: {e}")
    log(f"Finished in {time.time() - t0:.1f}s")
    return {"outputs": outputs, "errors": errors, "output_dir": out_dir}
