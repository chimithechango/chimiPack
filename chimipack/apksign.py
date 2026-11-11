"""Pure-Python APK signing (APK Signature Scheme v2) with a self-generated RSA key.

No external dependencies: RSA key generation, X.509 certificate creation and
PKCS#1 v1.5 signatures are implemented here with Python's big integers.
"""
import hashlib
import json
import os
import secrets
import struct
import time

# ----------------------------------------------------------------- RSA ----

_SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % d for d in range(3, int(p ** 0.5) + 1, 2))]


def _is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits):
    while True:
        c = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if _is_probable_prime(c):
            return c


def generate_rsa(bits=2048, e=65537):
    while True:
        p, q = _gen_prime(bits // 2), _gen_prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        return {"n": n, "e": e, "d": pow(e, -1, phi), "p": p, "q": q}


_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def rsa_sign_sha256(key, data):
    n, d = key["n"], key["d"]
    k = (n.bit_length() + 7) // 8
    t = _SHA256_DIGESTINFO + hashlib.sha256(data).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    p, q = key["p"], key["q"]
    m = int.from_bytes(em, "big")
    # CRT for speed
    dp, dq, qinv = d % (p - 1), d % (q - 1), pow(q, -1, p)
    m1, m2 = pow(m, dp, p), pow(m, dq, q)
    h = (qinv * (m1 - m2)) % p
    s = m2 + h * q
    return s.to_bytes(k, "big")


# ----------------------------------------------------------------- DER ----

def _der_len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, content):
    return bytes([tag]) + _der_len(len(content)) + content


def _int(v):
    b = v.to_bytes((v.bit_length() + 8) // 8 or 1, "big")
    return _tlv(0x02, b)


def _seq(*items):
    return _tlv(0x30, b"".join(items))


def _oid(dotted):
    parts = [int(x) for x in dotted.split(".")]
    out = bytes([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        enc = [p & 0x7F]
        p >>= 7
        while p:
            enc.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(enc))
    return _tlv(0x06, out)


_NULL = b"\x05\x00"
_RSA_ENC = _seq(_oid("1.2.840.113549.1.1.1"), _NULL)
_SHA256_RSA = _seq(_oid("1.2.840.113549.1.1.11"), _NULL)


def _name(cn, org):
    def rdn(oid, val):
        return _tlv(0x31, _seq(_oid(oid), _tlv(0x0C, val.encode("utf-8"))))
    return _seq(rdn("2.5.4.3", cn), rdn("2.5.4.10", org))


def _gtime(ts):
    return _tlv(0x18, time.strftime("%Y%m%d%H%M%SZ", time.gmtime(ts)).encode())


def public_key_der(key):
    rsa_pub = _seq(_int(key["n"]), _int(key["e"]))
    return _seq(_RSA_ENC, _tlv(0x03, b"\x00" + rsa_pub))


def make_certificate(key, cn="chimiPack", org="chimiPack"):
    now = int(time.time()) - 86400
    tbs = _seq(
        _tlv(0xA0, _int(2)),
        _int(secrets.randbits(63) + 1),
        _SHA256_RSA,
        _name(cn, org),
        _seq(_gtime(now), _gtime(now + 30 * 365 * 86400)),
        _name(cn, org),
        public_key_der(key),
    )
    sig = rsa_sign_sha256(key, tbs)
    return _seq(tbs, _SHA256_RSA, _tlv(0x03, b"\x00" + sig))


# ------------------------------------------------------------- keystore ----

def load_or_create_key(path, log=print):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        key = {k: int(raw[k], 16) for k in ("n", "e", "d", "p", "q")}
        key["cert"] = bytes.fromhex(raw["cert"])
        return key
    log("Generating your personal app-signing key (one time only)...")
    key = generate_rsa()
    key["cert"] = make_certificate(key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: format(key[k], "x") for k in ("n", "e", "d", "p", "q")} | {"cert": key["cert"].hex()}, f)
    return key


# ------------------------------------------------------------ v2 scheme ----

_CHUNK = 1024 * 1024
_ALGO_RSA_PKCS1_SHA256 = 0x0103
_V2_BLOCK_ID = 0x7109871A


def _lp(b):
    return struct.pack("<I", len(b)) + b


def _find_eocd(apk):
    idx = apk.rfind(b"PK\x05\x06")
    if idx < 0:
        raise ValueError("Not a zip file")
    cd_size, cd_off = struct.unpack("<II", apk[idx + 12: idx + 20])
    return idx, cd_off, cd_size


def _content_digest(sections):
    digests = []
    for sec in sections:
        for i in range(0, len(sec), _CHUNK):
            chunk = sec[i: i + _CHUNK]
            digests.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(chunk)) + chunk).digest())
    return hashlib.sha256(b"\x5a" + struct.pack("<I", len(digests)) + b"".join(digests)).digest()


def sign_apk_v2(apk: bytes, key) -> bytes:
    eocd_off, cd_off, cd_size = _find_eocd(apk)
    entries, cd, eocd = apk[:cd_off], apk[cd_off:eocd_off], apk[eocd_off:]
    digest = _content_digest([entries, cd, eocd])

    digests = _lp(_lp(struct.pack("<I", _ALGO_RSA_PKCS1_SHA256) + _lp(digest)))
    certs = _lp(_lp(key["cert"]))
    signed_data = digests + certs + _lp(b"")
    signature = rsa_sign_sha256(key, signed_data)
    signatures = _lp(_lp(struct.pack("<I", _ALGO_RSA_PKCS1_SHA256) + _lp(signature)))
    signer = _lp(signed_data) + signatures + _lp(public_key_der(key))
    v2_value = _lp(_lp(signer))

    pair = struct.pack("<Q", 4 + len(v2_value)) + struct.pack("<I", _V2_BLOCK_ID) + v2_value
    block_size = len(pair) + 8 + 16  # pairs + trailing size + magic
    block = struct.pack("<Q", block_size) + pair + struct.pack("<Q", block_size) + b"APK Sig Block 42"

    new_eocd = bytearray(eocd)
    struct.pack_into("<I", new_eocd, 16, cd_off + len(block))
    return entries + block + cd + bytes(new_eocd)
