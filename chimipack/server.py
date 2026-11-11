"""Local web server that powers the chimiPack window."""
import json
import mimetypes
import re
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, builder, bundle, electron, windows

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
SETTINGS = os.path.join(builder.HOME, "settings.json")
TOKEN = secrets.token_hex(16)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BRAND = "chimiPack"

_PICK = r'''
import sys, tkinter as tk
from tkinter import filedialog
r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True); r.update()
k, start = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None) or None
if k == "file":
    p = filedialog.askopenfilename(title="Choose an HTML file (or a .zip of your site)", initialdir=start,
        filetypes=[("Web page or zip", "*.html *.htm *.xhtml *.zip"), ("All files", "*.*")])
elif k == "icon":
    p = filedialog.askopenfilename(title="Choose an icon image", initialdir=start,
        filetypes=[("Images", "*.png *.jpg *.jpeg *.ico *.bmp *.gif"), ("All files", "*.*")])
else:
    p = filedialog.askdirectory(title="Choose the folder with your web app" if k == "folder" else "Where should the apps be saved?", initialdir=start)
sys.stdout.write(p or "")
'''

state = {"job": None, "last_ping": time.time(), "uploads": {}}
lock = threading.Lock()


DEFAULT_SETTINGS = {
    "theme": "system",            # system | light | dark
    "accent": "chimi",            # preset id (see ACCENTS in ui/index.html) or #rrggbb
    "output_dir": "",             # empty = Documents\chimiPack Builds
    "publisher": "",
    "icon_color": "auto",         # auto | #RRGGBB
    "open_after_build": False,
    "show_log": False,
    "targets": ["exe", "apk"],
}


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS, "r", encoding="utf-8-sig") as f:
            saved = json.load(f)
        s.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS and type(v) is type(DEFAULT_SETTINGS[k])})
    except Exception:
        pass
    return s


def save_settings(changes):
    s = load_settings()
    for k, v in changes.items():
        if k in DEFAULT_SETTINGS and type(v) is type(DEFAULT_SETTINGS[k]):
            s[k] = v
    if s["theme"] not in ("system", "light", "dark"):
        s["theme"] = "system"
    if not re.fullmatch(r"[a-z]{2,12}|#[0-9a-fA-F]{6}", s["accent"]):
        s["accent"] = "chimi"
    os.makedirs(builder.HOME, exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    return s


def pick(kind, start=None):
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-5] + ".exe" if os.path.exists(exe[:-5] + ".exe") else exe
    r = subprocess.run([exe, "-c", _PICK, kind, start or ""], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    return os.path.normpath(r.stdout.strip()) if r.stdout.strip() else ""


def describe(path):
    info = bundle.inspect(path)
    info["name_suggestion"] = info["title"]
    info["package_suggestion"] = builder.default_package(info["title"])
    return info


def start_job(opts):
    job = {"id": secrets.token_hex(4), "log": [], "done": False, "result": None, "error": None, "started": time.time()}

    def log(msg):
        job["log"].append(msg)

    def run():
        try:
            job["result"] = builder.run_build(opts, log)
        except Exception as e:
            job["error"] = str(e)
            log("ERROR: " + str(e))
            traceback.print_exc()
        finally:
            job["done"] = True

    with lock:
        if state["job"] and not state["job"]["done"]:
            raise RuntimeError("A build is already running.")
        state["job"] = job
    threading.Thread(target=run, daemon=True).start()
    return job["id"]


def reveal(path):
    if os.name == "nt":
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if os.path.isfile(path) else path])


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        state["last_ping"] = time.time()
        return self.headers.get("X-Token") == TOKEN

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path)
        state["last_ping"] = time.time()
        if u.path in ("/", "/index.html"):
            with open(os.path.join(UI_DIR, "index.html"), "rb") as f:
                html = f.read().replace(b"%%TOKEN%%", TOKEN.encode()).replace(b"%%VERSION%%", __version__.encode())
                s = load_settings()   # applied before first paint: no flash of the wrong theme/accent
                html = html.replace(b"%%THEME%%", s["theme"].encode()).replace(b"%%ACCENT%%", s["accent"].encode())
            return self._send(200, html, "text/html; charset=utf-8")
        if u.path == "/api/image":
            q = parse_qs(u.query)
            p = q.get("path", [""])[0]
            if q.get("t", [""])[0] == TOKEN and p.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".svg")) and os.path.isfile(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), mimetypes.guess_type(p)[0] or "application/octet-stream")
            return self._send(404, {"error": "not found"})
        if not self._authorized():
            return self._send(403, {"error": "forbidden"})
        if u.path == "/api/env":
            csc = windows.find_csc() if os.name == "nt" else None
            return self._send(200, {"windows_ok": bool(csc), "settings": load_settings(),
                                    "default_output": builder.DEFAULT_OUTPUT, "key_path": builder.KEY_PATH,
                                    "key_exists": os.path.exists(builder.KEY_PATH), "version": __version__,
                                    "electron_version": electron.ELECTRON_VERSION, "platform": sys.platform})
        if u.path == "/api/job":
            job = state["job"]
            if not job:
                return self._send(200, {"job": None})
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            return self._send(200, {"id": job["id"], "log": job["log"][since:], "done": job["done"],
                                    "result": job["result"], "error": job["error"]})
        if u.path == "/api/ping":
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def do_PUT(self):
        if not self._authorized():
            return self._send(403, {"error": "forbidden"})
        parts = urlparse(self.path).path.split("/", 4)  # ['', 'api', 'upload', id, rel]
        if len(parts) == 5 and parts[2] == "upload" and parts[3] in state["uploads"]:
            base = state["uploads"][parts[3]]
            rel = unquote(parts[4]).replace("\\", "/")
            target = os.path.normpath(os.path.join(base, rel))
            if not target.startswith(base + os.sep):
                return self._send(400, {"error": "bad path"})
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(self._body())
            return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorized():
            return self._send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        try:
            data = json.loads(self._body() or b"{}")
            if u.path == "/api/pick":
                return self._send(200, {"path": pick(data.get("kind", "file"), data.get("start"))})
            if u.path == "/api/inspect":
                return self._send(200, describe(data["path"]))
            if u.path == "/api/upload/start":
                uid = secrets.token_hex(6)
                state["uploads"][uid] = tempfile.mkdtemp(prefix="chimipack_drop_")
                return self._send(200, {"id": uid, "dir": state["uploads"][uid]})
            if u.path == "/api/build":
                return self._send(200, {"id": start_job(data)})
            if u.path == "/api/reveal":
                reveal(data["path"])
                return self._send(200, {"ok": True})
            if u.path == "/api/settings":
                return self._send(200, save_settings(data))
        except Exception as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})


def _with_progress_window(task):
    """Run task(progress) while showing a small download window (only used on first start)."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    result = {}
    root = tk.Tk()
    root.title(BRAND)
    root.geometry("420x120")
    root.resizable(False, False)
    ttk.Label(root, text=f"Setting up {BRAND} (first start only)", font=("Segoe UI", 11, "bold")).pack(pady=(16, 4))
    status = ttk.Label(root, text="Downloading Electron...")
    status.pack()
    bar = ttk.Progressbar(root, length=360, maximum=100)
    bar.pack(pady=10)
    prog = {"done": 0, "total": 0}

    def run():
        try:
            result["value"] = task(lambda d, t: prog.update(done=d, total=t))
        except Exception as e:
            result["error"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()

    def tick():
        if prog["total"]:
            bar["value"] = 100 * prog["done"] / prog["total"]
            status["text"] = f"Downloading Electron... {prog['done'] // 1048576} / {prog['total'] // 1048576} MB"
        if th.is_alive():
            root.after(150, tick)
        else:
            root.destroy()
    tick()
    root.mainloop()
    if "error" in result:
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(BRAND, f"{BRAND} needs to download Electron once (about 110 MB) "
                             "but couldn't:\n\n" + str(result["error"]) + "\n\nCheck your internet connection and try again.")
        r.destroy()
        raise SystemExit(1)
    return result["value"]


def converter_window_exe():
    """Build (once) the Electron app that shows the converter UI."""
    from . import electron, icons
    shell_dir = os.path.join(os.path.dirname(__file__), "data", "ui-shell")
    files = {}
    for f in os.listdir(shell_dir):
        with open(os.path.join(shell_dir, f), "rb") as fh:
            files[f] = fh.read()
    files["package.json"] = b'{"name":"chimipack","productName":"chimiPack","version":"' + __version__.encode() + \
        b'","main":"main.js","private":true}'
    import hashlib
    key = hashlib.sha256(b"".join(files[k] for k in sorted(files)) + electron.RUNTIME_KEY.encode()).hexdigest()[:10]
    dest = os.path.join(electron.CACHE, "chimipack-" + key)
    exe = os.path.join(dest, BRAND + ".exe")
    if os.path.exists(os.path.join(dest, ".complete")):
        return exe
    icon_set = icons.make_icon_set(None, BRAND, log=lambda *a: None, color=icons.CHIMI_ORANGE)
    if icon_set:
        files["icon.ico"] = icons.build_ico(icon_set)
    if not os.path.exists(os.path.join(electron.CACHE, electron.RUNTIME_KEY, ".complete")):
        _with_progress_window(lambda progress: electron.runtime_dir(progress, log=lambda *a: None))
    return electron.assemble_app(dest, BRAND + ".exe", files, log=lambda *a: None)


def main():
    class Server(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
                super().handle_error(request, client_address)

    srv = Server(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{BRAND} running at {url}", flush=True)
    if "--no-open" in sys.argv:  # developer mode: just serve
        threading.Event().wait()
    exe = converter_window_exe()
    subprocess.run([exe, f"--chimi-url={url}"])
    # Let a running build finish so no half-written files are left behind.
    while state["job"] and not state["job"]["done"]:
        time.sleep(1)


if __name__ == "__main__":
    main()
