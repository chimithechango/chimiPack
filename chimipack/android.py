"""Builds a signed Android .apk without the Android SDK.

The APK contains a tiny pre-compiled WebView launcher (data/launcher.dex), a
binary AndroidManifest.xml and resources.arsc generated here, the app icon and
the user's web files under assets/www.
"""
import os
import struct

from . import apksign
from .ziputil import ZipWriter

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ATTR_IDS = {
    "theme": 0x01010000, "label": 0x01010001, "icon": 0x01010002, "name": 0x01010003,
    "exported": 0x01010010, "screenOrientation": 0x0101001E, "configChanges": 0x0101001F,
    "minSdkVersion": 0x0101020C, "versionCode": 0x0101021B, "versionName": 0x0101021C,
    "targetSdkVersion": 0x01010270, "hardwareAccelerated": 0x010102D3,
    "usesCleartextTraffic": 0x010104EC, "roundIcon": 0x0101052C,
}
T_REF, T_STRING, T_INT, T_BOOL = 0x01, 0x03, 0x10, 0x12
ORIENTATIONS = {"auto": -1, "portrait": 7, "landscape": 6}
ICON_RES_ID = 0x7F010000
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ------------------------------------------------------- string pool ------

def _string_pool(strings, utf8=False):
    offsets, data = [], bytearray()
    for s in strings:
        offsets.append(len(data))
        if utf8:
            b = s.encode("utf-8")
            for n in (len(s), len(b)):
                data += bytes([0x80 | (n >> 8), n & 0xFF]) if n > 0x7F else bytes([n])
            data += b + b"\x00"
        else:
            u = s.encode("utf-16-le")
            data += struct.pack("<H", len(u) // 2) + u + b"\x00\x00"
    while len(data) % 4:
        data += b"\x00"
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    flags = 0x100 if utf8 else 0
    body = b"".join(struct.pack("<I", o) for o in offsets) + bytes(data)
    return struct.pack("<HHIIIIII", 0x0001, header_size, header_size + len(body), len(strings), 0, flags,
                       strings_start, 0) + body


# --------------------------------------------------------- binary XML ------

class _Elem:
    def __init__(self, tag, attrs=(), children=()):
        self.tag, self.attrs, self.children = tag, list(attrs), list(children)


def _A(name, value, ns=True):
    return (name, value, ns)


def _encode_axml(root):
    # Attribute names that have resource IDs must come first (resource map order).
    attr_names, others = [], []

    def visit(e):
        for name, value, ns in e.attrs:
            if ns and name in ATTR_IDS:
                if name not in attr_names:
                    attr_names.append(name)
            elif name not in others:
                others.append(name)
            if isinstance(value, str) and value not in others:
                others.append(value)
        if e.tag not in others:
            others.append(e.tag)
        for c in e.children:
            visit(c)
    visit(root)
    for s in ("android", ANDROID_NS):
        if s not in others:
            others.append(s)
    strings = attr_names + [s for s in others if s not in attr_names]
    idx = {s: i for i, s in enumerate(strings)}

    chunks = bytearray()

    def node(type_, ext):
        return struct.pack("<HHIIi", type_, 16, 16 + len(ext), 1, -1) + ext

    chunks += node(0x0100, struct.pack("<ii", idx["android"], idx[ANDROID_NS]))

    def emit(e):
        attrs = sorted(e.attrs, key=lambda a: ATTR_IDS.get(a[0], 0x7FFFFFFF) if a[2] else -1)
        body = b""
        for name, value, ns in attrs:
            ns_i = idx[ANDROID_NS] if ns else -1
            if isinstance(value, bool):
                raw, typ, data = -1, T_BOOL, 0xFFFFFFFF if value else 0
            elif isinstance(value, int):
                raw, typ, data = -1, T_INT, value & 0xFFFFFFFF
            elif isinstance(value, tuple) and value[0] == "ref":
                raw, typ, data = -1, T_REF, value[1]
            else:
                raw, typ, data = idx[value], T_STRING, idx[value]
            body += struct.pack("<iiiHBBI", ns_i, idx[name], raw, 8, 0, typ, data)
        ext = struct.pack("<iiHHHHHH", -1, idx[e.tag], 20, 20, len(attrs), 0, 0, 0) + body
        chunks.extend(node(0x0102, ext))
        for c in e.children:
            emit(c)
        chunks.extend(node(0x0103, struct.pack("<ii", -1, idx[e.tag])))

    emit(root)
    chunks += node(0x0101, struct.pack("<ii", idx["android"], idx[ANDROID_NS]))

    pool = _string_pool(strings)
    resmap = struct.pack("<HHI", 0x0180, 8, 8 + 4 * len(attr_names)) + b"".join(
        struct.pack("<I", ATTR_IDS[n]) for n in attr_names)
    body = pool + resmap + bytes(chunks)
    return struct.pack("<HHI", 0x0003, 8, 8 + len(body)) + body


def build_manifest(package, label, version_name, version_code, orientation, has_icon):
    app_attrs = [_A("label", label), _A("hardwareAccelerated", True), _A("usesCleartextTraffic", True)]
    if has_icon:
        app_attrs += [_A("icon", ("ref", ICON_RES_ID)), _A("roundIcon", ("ref", ICON_RES_ID))]
    activity = _Elem("activity", [
        _A("name", "app.chimipack.MainActivity"), _A("exported", True), _A("label", label),
        _A("screenOrientation", ORIENTATIONS.get(orientation, -1)), _A("configChanges", 0x1FF0),
    ], [_Elem("intent-filter", [], [
        _Elem("action", [_A("name", "android.intent.action.MAIN")]),
        _Elem("category", [_A("name", "android.intent.category.LAUNCHER")]),
    ])])
    root = _Elem("manifest", [
        _A("versionCode", int(version_code)), _A("versionName", version_name),
        _A("package", package, ns=False),
    ], [
        _Elem("uses-sdk", [_A("minSdkVersion", 24), _A("targetSdkVersion", 34)]),
        _Elem("uses-permission", [_A("name", "android.permission.INTERNET")]),
        _Elem("uses-permission", [_A("name", "android.permission.ACCESS_NETWORK_STATE")]),
        _Elem("application", app_attrs, [activity]),
    ])
    return _encode_axml(root)


# ------------------------------------------------------ resources.arsc ------

def build_arsc(package, icon_path="res/mipmap/ic_launcher.png"):
    global_pool = _string_pool([icon_path], utf8=True)
    type_pool = _string_pool(["mipmap"], utf8=True)
    key_pool = _string_pool(["ic_launcher"], utf8=True)

    spec = struct.pack("<HHIBBHI", 0x0202, 16, 16 + 4, 1, 0, 0, 1) + struct.pack("<I", 0)
    config = struct.pack("<I", 64) + b"\x00" * 60
    type_header_size = 8 + 4 + 4 + 4 + len(config)
    entries = struct.pack("<I", 0)
    entry = struct.pack("<HHI", 8, 0, 0) + struct.pack("<HBBI", 8, 0, T_STRING, 0)
    entries_start = type_header_size + len(entries)
    type_chunk = struct.pack("<HHIBBHII", 0x0201, type_header_size, entries_start + len(entry), 1, 0, 0, 1,
                             entries_start) + config + entries + entry

    name = package.encode("utf-16-le")[:254].ljust(256, b"\x00")
    pkg_header_size = 288
    type_strings_off = pkg_header_size
    key_strings_off = type_strings_off + len(type_pool)
    pkg_body = type_pool + key_pool + spec + type_chunk
    pkg = struct.pack("<HHII", 0x0200, pkg_header_size, pkg_header_size + len(pkg_body), 0x7F) + name + \
        struct.pack("<IIIII", type_strings_off, 1, key_strings_off, 1, 0) + pkg_body
    body = global_pool + pkg
    return struct.pack("<HHII", 0x0002, 12, 12 + len(body), 1) + body


# ------------------------------------------------------------- build ------

def build_apk(cfg, files, icon_set, out_path, key_path, log=print):
    package = cfg["package"]
    has_icon = bool(icon_set)
    z = ZipWriter()
    z.add("AndroidManifest.xml", build_manifest(package, cfg["name"], cfg["version"], cfg["version_code"],
                                                cfg.get("orientation", "auto"), has_icon), compress=True)
    with open(os.path.join(DATA_DIR, "launcher.dex"), "rb") as f:
        z.add("classes.dex", f.read(), compress=True)
    if has_icon:
        z.add("resources.arsc", build_arsc(package), compress=False)
        z.add("res/mipmap/ic_launcher.png", icon_set.get(192) or icon_set[max(icon_set)], compress=False)
    z.add("assets/chimipack.cfg", f"entry={cfg['entry']}\nfullscreen={1 if cfg.get('fullscreen') else 0}\n"
          .encode("utf-8"), compress=True)
    total = len(files)
    for i, (rel, full) in enumerate(sorted(files.items())):
        with open(full, "rb") as f:
            z.add("assets/www/" + rel, f.read())
        if total > 50 and i % max(1, total // 10) == 0:
            log(f"  packed {i}/{total} files")
    unsigned = z.finish()
    key = apksign.load_or_create_key(key_path, log)
    log("Signing APK (v2 signature)...")
    signed = apksign.sign_apk_v2(unsigned, key)
    with open(out_path, "wb") as f:
        f.write(signed)
    return out_path
