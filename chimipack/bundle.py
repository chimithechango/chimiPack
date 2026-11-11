"""Collects the web files that make up an app (HTML entry + its JS/CSS/images/...)."""
import os
import re
import tempfile
import zipfile
from urllib.parse import unquote

SKIP_DIRS = {".git", ".svn", ".hg", "__pycache__", ".idea", ".vscode", "node_modules"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
HTML_EXT = (".html", ".htm", ".xhtml")
BIG_FOLDER_BYTES = 300 * 1024 * 1024
BIG_FOLDER_FILES = 5000

_ATTR_RE = re.compile(r"""(?:src|href|data|poster|content|srcset|data-src)\s*=\s*["']([^"']+)["']""", re.I)
_CSS_URL_RE = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.I)
_CSS_IMPORT_RE = re.compile(r"""@import\s+["']([^"']+)["']""", re.I)
_JS_PATH_RE = re.compile(
    r"""["'`]([^"'`\s<>{}]+\.(?:js|mjs|json|css|html?|png|jpe?g|gif|webp|svg|ico|bmp|mp3|ogg|wav|m4a|mp4|webm|"""
    r"""woff2?|ttf|otf|wasm|txt|xml|glb|gltf|bin|obj|atlas|fnt|csv|tmx|tsx|data|pck))["'`]""", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_ICON_RE = re.compile(r"""<link[^>]+rel=["'][^"']*icon[^"']*["'][^>]*>""", re.I)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def _walk(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in SKIP_FILES:
                continue
            full = os.path.join(root, f)
            yield os.path.relpath(full, folder).replace("\\", "/"), full


def folder_stats(folder, limit_files=BIG_FOLDER_FILES + 1):
    count, size = 0, 0
    for _, full in _walk(folder):
        count += 1
        try:
            size += os.path.getsize(full)
        except OSError:
            pass
        if count >= limit_files:
            break
    return count, size


def _read_text(path):
    try:
        with open(path, "rb") as f:
            return f.read(8 * 1024 * 1024).decode("utf-8", "replace")
    except OSError:
        return ""


def referenced_files(root, entry_rel):
    """Follow references from the entry HTML (and the CSS/JS/HTML it pulls in)."""
    found, queue = {}, [entry_rel]
    while queue:
        rel = queue.pop()
        if rel in found:
            continue
        full = os.path.normpath(os.path.join(root, rel))
        if not os.path.isfile(full) or not full.startswith(os.path.normpath(root)):
            continue
        found[rel] = full
        ext = rel.lower().rsplit(".", 1)[-1]
        if ext not in ("html", "htm", "xhtml", "css", "js", "mjs", "json", "svg"):
            continue
        text = _read_text(full)
        cands = []
        if ext in ("html", "htm", "xhtml", "svg"):
            for m in _ATTR_RE.findall(text):
                cands += [part.strip().split(" ")[0] for part in m.split(",")]
        cands += _CSS_URL_RE.findall(text) + _CSS_IMPORT_RE.findall(text)
        if ext in ("js", "mjs", "html", "htm", "json"):
            cands += _JS_PATH_RE.findall(text)
            cands += re.findall(r"""(?:import|from)\s*\(?\s*["']([^"']+)["']""", text)
        base = os.path.dirname(rel)
        for c in cands:
            c = unquote(c.split("#")[0].split("?")[0]).strip()
            if not c or re.match(r"^[a-z][a-z0-9+.-]*:", c, re.I) or c.startswith("//"):
                continue
            target = c.lstrip("/") if c.startswith("/") else os.path.join(base, c)
            target = os.path.normpath(target).replace("\\", "/")
            if target.startswith(".."):
                continue
            # Some paths are relative to the site root rather than the file
            for t in (target, os.path.normpath(c.lstrip("./")).replace("\\", "/")):
                if os.path.isfile(os.path.join(root, t)) and t not in found:
                    queue.append(t)
                    break
    return found


def extract_zip(path):
    dest = tempfile.mkdtemp(prefix="chimipack_zip_")
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            target = os.path.normpath(os.path.join(dest, info.filename))
            if not target.startswith(dest):
                continue  # zip-slip protection
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    # If the zip contains a single top-level folder, use it as root
    items = [i for i in os.listdir(dest) if i not in SKIP_FILES and i != "__MACOSX"]
    if len(items) == 1 and os.path.isdir(os.path.join(dest, items[0])):
        return os.path.join(dest, items[0])
    return dest


def inspect(path):
    """Describe an input (HTML file, folder or .zip) for the UI."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.isfile(path) and path.lower().endswith(".zip"):
        root = extract_zip(path)
        entry = None
        kind = "zip"
    elif os.path.isdir(path):
        root, entry, kind = path, None, "folder"
    else:
        root, entry, kind = os.path.dirname(path), os.path.basename(path), "file"

    htmls = []
    for rel, _ in _walk(root):
        if rel.lower().endswith(HTML_EXT):
            htmls.append(rel)
        if len(htmls) > 200:
            break
    htmls.sort(key=lambda r: (r.count("/"), r.lower() not in ("index.html", "index.htm"), r.lower()))
    if not entry:
        if not htmls:
            raise ValueError("No .html file was found in that folder.")
        entry = htmls[0]

    count, size = folder_stats(root)
    big = count > BIG_FOLDER_FILES or size > BIG_FOLDER_BYTES
    refs = referenced_files(root, entry)
    text = _read_text(os.path.join(root, entry))
    t = _TITLE_RE.search(text)
    title = re.sub(r"\s+", " ", t.group(1)).strip() if t else ""
    if not title:
        title = os.path.splitext(os.path.basename(entry))[0]
        if title.lower() == "index":
            title = os.path.basename(root.rstrip("\\/")) or "My App"
    icon = None
    for tag in _ICON_RE.findall(text):
        h = _HREF_RE.search(tag)
        if h:
            cand = os.path.normpath(os.path.join(root, os.path.dirname(entry), unquote(h.group(1))))
            if os.path.isfile(cand) and cand.lower().endswith((".png", ".ico", ".jpg", ".jpeg", ".bmp", ".gif")):
                icon = cand
                break
    return {
        "input": path, "kind": kind, "root": root, "entry": entry, "html_files": htmls[:200],
        "folder_files": count, "folder_bytes": size, "folder_is_big": big,
        "referenced_files": len(refs), "referenced_bytes": sum(os.path.getsize(p) for p in refs.values()),
        "suggested_mode": "referenced" if (big and kind == "file") else "folder",
        "title": title[:60], "icon": icon,
    }


def collect(root, entry, mode="folder"):
    """Return {relative_path: absolute_path} for everything to ship."""
    if mode == "referenced":
        files = referenced_files(root, entry)
    elif mode == "single":
        files = {entry: os.path.join(root, entry)}
    else:
        files = dict(_walk(root))
    if entry not in files:
        files[entry] = os.path.join(root, entry)
    return files
