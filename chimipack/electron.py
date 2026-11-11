"""Downloads, verifies and caches the Electron runtime used by the converter window
and by every Windows .exe chimiPack builds."""
import hashlib
import os
import shutil
import urllib.request
import zipfile

ELECTRON_VERSION = "44.9.3"
PLATFORM = "win32-x64"
CACHE = os.path.join(os.path.expanduser("~"), ".chimipack", "electron")
_BASE = f"https://github.com/electron/electron/releases/download/v{ELECTRON_VERSION}/"
_ZIP_NAME = f"electron-v{ELECTRON_VERSION}-{PLATFORM}.zip"
RUNTIME_KEY = f"electron-{ELECTRON_VERSION}-{PLATFORM}-1"  # bump the suffix if trimming rules change


def _fetch(url, dest=None, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "chimiPack"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if dest is None:
            return r.read()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


def download_zip(progress=None, log=print):
    """Return the path of the official Electron zip, downloading + verifying it once."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, _ZIP_NAME)
    if os.path.exists(path):
        return path
    log(f"Downloading Electron {ELECTRON_VERSION} (one time only, about 110 MB)...")
    sums = _fetch(_BASE + "SHASUMS256.txt").decode("utf-8", "replace")
    expected = next((ln.split()[0] for ln in sums.splitlines() if ln.strip().endswith(_ZIP_NAME)), None)
    if not expected:
        raise RuntimeError("Couldn't find the Electron checksum for " + _ZIP_NAME)
    tmp = path + ".part"
    _fetch(_BASE + _ZIP_NAME, tmp, progress)
    h = hashlib.sha256()
    with open(tmp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest().lower() != expected.lower():
        os.remove(tmp)
        raise RuntimeError("The Electron download was corrupted (checksum mismatch). Please try again.")
    os.replace(tmp, path)
    log("  Electron downloaded and verified.")
    return path


def _keep(name):
    n = name.replace("\\", "/")
    if n.startswith("locales/") and n not in ("locales/en-US.pak",):
        return False
    if n in ("resources/default_app.asar",):
        return False
    return not n.endswith("/")


def runtime_dir(progress=None, log=print):
    """Extracted runtime (shared by the converter window)."""
    d = os.path.join(CACHE, RUNTIME_KEY)
    if os.path.exists(os.path.join(d, ".complete")):
        return d
    z = download_zip(progress, log)
    tmp = d + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            if _keep(info.filename):
                zf.extract(info, tmp)
    shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, d)
    open(os.path.join(d, ".complete"), "w").close()
    return d


def trimmed_zip(log=print):
    """Runtime re-packed without unused locales; embedded into every .exe."""
    out = os.path.join(CACHE, RUNTIME_KEY + ".zip")
    if os.path.exists(out):
        return out
    src = download_zip(log=log)
    log("Preparing the Electron runtime for packaging (one time only)...")
    tmp = out + ".part"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zout:
        for info in zin.infolist():
            if _keep(info.filename):
                zout.writestr(info.filename, zin.read(info))
    os.replace(tmp, out)
    return out


def assemble_app(dest, exe_name, app_files, progress=None, log=print):
    """Create a runnable Electron app folder: hard-links to the shared runtime (no extra
    disk space) with electron.exe renamed, plus app files in resources/app."""
    rt = runtime_dir(progress, log)
    if os.path.exists(os.path.join(dest, ".complete")):
        return os.path.join(dest, exe_name)
    tmp = dest + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    for root, _, files in os.walk(rt):
        for f in files:
            if f == ".complete":
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, rt)
            if rel.lower() == "electron.exe":
                rel = exe_name
            target = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                os.link(src, target)
            except OSError:
                shutil.copy2(src, target)
    for rel, data in app_files.items():
        target = os.path.join(tmp, "resources", "app", rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(data)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    open(os.path.join(dest, ".complete"), "w").close()
    return os.path.join(dest, exe_name)
