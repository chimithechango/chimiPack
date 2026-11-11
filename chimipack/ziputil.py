"""Small deterministic ZIP writer with zipalign-style 4-byte alignment for stored entries."""
import struct
import zlib

ALREADY_COMPRESSED = {
    "png", "jpg", "jpeg", "gif", "webp", "mp3", "ogg", "m4a", "aac", "mp4", "webm",
    "zip", "gz", "woff", "woff2", "opus", "flac", "avif", "jar", "apk",
}

_DOS_TIME = (0 << 11) | (0 << 5)            # 00:00
_DOS_DATE = ((2024 - 1980) << 9) | (1 << 5) | 1  # 2024-01-01


class ZipWriter:
    def __init__(self):
        self.buf = bytearray()
        self.central = []

    def add(self, name, data: bytes, compress=None, align=4, mode=None):
        name_b = name.replace("\\", "/").encode("utf-8")
        if compress is None:
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            compress = ext not in ALREADY_COMPRESSED and len(data) > 0
        crc = zlib.crc32(data) & 0xFFFFFFFF
        if compress:
            co = zlib.compressobj(9, zlib.DEFLATED, -15)
            payload = co.compress(data) + co.flush()
            if len(payload) >= len(data):
                compress, payload = False, data
        else:
            payload = data
        method = 8 if compress else 0
        offset = len(self.buf)
        extra = b""
        if not compress and align:
            pad = (align - (offset + 30 + len(name_b)) % align) % align
            extra = b"\x00" * pad
        flags = 0x0800  # UTF-8 names
        self.buf += struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, flags, method, _DOS_TIME, _DOS_DATE,
                                crc, len(payload), len(data), len(name_b), len(extra))
        self.buf += name_b + extra + payload
        self.central.append((name_b, method, crc, len(payload), len(data), offset, flags, mode))

    def finish(self) -> bytes:
        cd = bytearray()
        for name_b, method, crc, csize, usize, offset, flags, mode in self.central:
            made_by = (3 << 8) | 20 if mode is not None else 20       # 3 = Unix, keeps permissions
            ext_attr = ((0o100000 | mode) << 16) if mode is not None else 0
            cd += struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, made_by, 20, flags, method, _DOS_TIME, _DOS_DATE,
                              crc, csize, usize, len(name_b), 0, 0, 0, 0, ext_attr, offset)
            cd += name_b
        cd_off = len(self.buf)
        out = self.buf + cd
        out += struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(self.central), len(self.central),
                           len(cd), cd_off, 0)
        return bytes(out)
