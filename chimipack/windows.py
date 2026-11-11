"""Builds a single-file Windows .exe that runs the web app in Electron (no browser involved).

The small launcher is compiled with the C# compiler that ships with Windows; the Electron
runtime and the app files are appended to it.
"""
import glob
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile

from . import electron
from .icons import build_ico
from .ziputil import ZipWriter

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def find_csc():
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for fw in ("Framework64", "Framework"):
        cands = sorted(glob.glob(os.path.join(windir, "Microsoft.NET", fw, "v4.*", "csc.exe")), reverse=True)
        if cands:
            return cands[0]
    return None


def _cs_str(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", " ")


def _version4(v):
    nums = [int(x) for x in re.findall(r"\d+", v)][:4]
    while len(nums) < 4:
        nums.append(0)
    return ".".join(str(min(n, 65534)) for n in nums)


def exe_name(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return (s or "App") + ".exe"


def electron_app_files(cfg, files, icon_set):
    """{relative path: bytes} for resources/app of an Electron app."""
    out = {}
    with open(os.path.join(DATA_DIR, "electron-app", "main.js"), "rb") as f:
        out["main.js"] = f.read()
    slug = re.sub(r"[^a-z0-9-]+", "-", cfg["package"].lower()).strip("-") or "app"
    out["package.json"] = json.dumps({"name": slug, "productName": cfg["name"], "version": "1.0.0",
                                      "main": "main.js", "private": True}, indent=2).encode()
    out["chimipack.json"] = json.dumps({"id": cfg["package"], "name": cfg["name"], "entry": cfg["entry"],
                                  "width": int(cfg.get("width", 1200)), "height": int(cfg.get("height", 800)),
                                  "fullscreen": bool(cfg.get("fullscreen"))}, indent=2).encode()
    if icon_set:
        out["icon.png"] = icon_set.get(256) or icon_set[max(icon_set)]
        out["icon.ico"] = build_ico(icon_set)
    for rel, full in files.items():
        with open(full, "rb") as f:
            out["www/" + rel] = f.read()
    return out


def compile_stub(cfg, icon_set, out_path, app_key, log=print):
    csc = find_csc()
    if not csc:
        raise RuntimeError("The .NET Framework C# compiler (csc.exe) was not found. "
                           "Windows .exe builds need Windows 10/11 (it's built in).")
    work = tempfile.mkdtemp(prefix="chimipack_win_")
    with open(os.path.join(DATA_DIR, "ElectronStub.cs"), "r", encoding="utf-8") as f:
        src = f.read()
    repl = {
        "%%NAME%%": _cs_str(cfg["name"]), "%%APPID%%": _cs_str(cfg["package"]),
        "%%EXENAME%%": _cs_str(exe_name(cfg["name"])), "%%RTKEY%%": electron.RUNTIME_KEY,
        "%%APPKEY%%": app_key, "%%PUBLISHER%%": _cs_str(cfg.get("publisher") or cfg["name"]),
        "%%VERSION4%%": _version4(cfg["version"]),
    }
    for k, v in repl.items():
        src = src.replace(k, v)
    cs = os.path.join(work, "Program.cs")
    with open(cs, "w", encoding="utf-8") as f:
        f.write(src)
    args = [csc, "/nologo", "/target:winexe", "/optimize+", "/platform:x64", "/out:" + out_path,
            "/r:System.IO.Compression.dll", "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll"]
    if icon_set:
        ico = os.path.join(work, "app.ico")
        with open(ico, "wb") as f:
            f.write(build_ico(icon_set))
        args.append("/win32icon:" + ico)
    args.append(cs)
    r = subprocess.run(args, capture_output=True, text=True, creationflags=0x08000000)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("C# compiler failed:\n" + (r.stdout + r.stderr).strip()[-2000:])


def build_exe(cfg, files, icon_set, out_path, log=print):
    runtime_zip = electron.trimmed_zip(log)

    z = ZipWriter()
    for rel, data in sorted(electron_app_files(cfg, files, icon_set).items()):
        z.add(rel, data, align=0)
    app_zip = z.finish()
    app_key = hashlib.sha256(app_zip + electron.RUNTIME_KEY.encode()).hexdigest()[:12]

    log("Compiling Windows launcher...")
    stub = out_path + ".stub"
    compile_stub(cfg, icon_set, stub, app_key, log)
    log(f"Packing Electron {electron.ELECTRON_VERSION} + your app into one .exe...")
    tmp = out_path + ".part"
    with open(tmp, "wb") as out:
        with open(stub, "rb") as f:
            out.write(f.read())
        rt_off = out.tell()
        with open(runtime_zip, "rb") as f:
            while True:
                chunk = f.read(1 << 22)
                if not chunk:
                    break
                out.write(chunk)
        rt_len = out.tell() - rt_off
        app_off = out.tell()
        out.write(app_zip)
        out.write(struct.pack("<qqqq", rt_off, rt_len, app_off, len(app_zip)) + b"CHIMIPK1")
    os.remove(stub)
    os.replace(tmp, out_path)
    return out_path
