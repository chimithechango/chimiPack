"""Icon handling: normalise any image into square PNGs of several sizes, build .ico files,
and draw a default icon (solid color + initial) when the user doesn't supply one."""
import os
import re
import struct
import subprocess
import tempfile

SIZES = (16, 24, 32, 48, 64, 128, 192, 256, 512)

_PS_SCRIPT = r"""
Add-Type -AssemblyName System.Drawing
$src = $env:CHIMI_SRC; $out = $env:CHIMI_OUT; $letter = $env:CHIMI_LETTER
$c1 = [System.Drawing.ColorTranslator]::FromHtml($env:CHIMI_C1)
$fgBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.ColorTranslator]::FromHtml($env:CHIMI_FG))
$master = New-Object System.Drawing.Bitmap 512, 512
$g = [System.Drawing.Graphics]::FromImage($master)
$g.SmoothingMode = 'AntiAlias'; $g.InterpolationMode = 'HighQualityBicubic'; $g.PixelOffsetMode = 'HighQuality'; $g.TextRenderingHint = 'AntiAliasGridFit'
$g.Clear([System.Drawing.Color]::Transparent)
if ($src) {
  $img = [System.Drawing.Image]::FromFile($src)
  $s = [Math]::Min(512 / $img.Width, 512 / $img.Height)
  $w = [int]($img.Width * $s); $h = [int]($img.Height * $s)
  $g.DrawImage($img, [int]((512 - $w) / 2), [int]((512 - $h) / 2), $w, $h)
  $img.Dispose()
} else {
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $r = 112; $x = 16; $y = 16; $d = 480
  $path.AddArc($x, $y, $r, $r, 180, 90); $path.AddArc($x + $d - $r, $y, $r, $r, 270, 90)
  $path.AddArc($x + $d - $r, $y + $d - $r, $r, $r, 0, 90); $path.AddArc($x, $y + $d - $r, $r, $r, 90, 90); $path.CloseFigure()
  $brush = New-Object System.Drawing.SolidBrush $c1
  $g.FillPath($brush, $path)
  $font = New-Object System.Drawing.Font 'Segoe UI Semibold', 230, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
  $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
  $g.DrawString($letter, $font, $fgBrush, (New-Object System.Drawing.RectangleF 0, 10, 512, 512), $fmt)
}
$g.Dispose()
foreach ($size in $env:CHIMI_SIZES.Split(',')) {
  $n = [int]$size
  $bmp = New-Object System.Drawing.Bitmap $n, $n
  $gg = [System.Drawing.Graphics]::FromImage($bmp)
  $gg.InterpolationMode = 'HighQualityBicubic'; $gg.SmoothingMode = 'AntiAlias'; $gg.PixelOffsetMode = 'HighQuality'
  $gg.DrawImage($master, 0, 0, $n, $n); $gg.Dispose()
  $bmp.Save((Join-Path $out "icon_$n.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
}
# iOS: opaque, full-bleed squares (iOS applies its own rounded mask).
$ios = New-Object System.Drawing.Bitmap 1024, 1024
$g = [System.Drawing.Graphics]::FromImage($ios)
$g.SmoothingMode = 'AntiAlias'; $g.InterpolationMode = 'HighQualityBicubic'; $g.PixelOffsetMode = 'HighQuality'; $g.TextRenderingHint = 'AntiAliasGridFit'
if ($src) {
  $g.Clear([System.Drawing.Color]::White)
  $img = [System.Drawing.Image]::FromFile($src)
  $s = [Math]::Min(1024 / $img.Width, 1024 / $img.Height)
  $w = [int]($img.Width * $s); $h = [int]($img.Height * $s)
  $g.DrawImage($img, [int]((1024 - $w) / 2), [int]((1024 - $h) / 2), $w, $h); $img.Dispose()
} else {
  $g.Clear($c1)
  $font = New-Object System.Drawing.Font 'Segoe UI Semibold', 470, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
  $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'
  $g.DrawString($letter, $font, $fgBrush, (New-Object System.Drawing.RectangleF 0, 20, 1024, 1024), $fmt)
}
$g.Dispose()
foreach ($size in $env:CHIMI_IOS_SIZES.Split(',')) {
  $n = [int]$size
  $bmp = New-Object System.Drawing.Bitmap $n, $n, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
  $gg = [System.Drawing.Graphics]::FromImage($bmp)
  $gg.InterpolationMode = 'HighQualityBicubic'; $gg.PixelOffsetMode = 'HighQuality'
  $gg.DrawImage($ios, 0, 0, $n, $n); $gg.Dispose()
  $bmp.Save((Join-Path $out "ios_$n.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
}
$ios.Dispose()
$master.Dispose()
"""
IOS_SIZES = (120, 152, 167, 180, 1024)

# Solid colors for generated icons ("auto" picks one from the app name). Keep in sync with ui/index.html.
COLORS = ["#E4572E", "#2F6FDE", "#2E8B57", "#7A4FBF", "#D4930D", "#C0306A"]
CHIMI_ORANGE = "#E4572E"


def _luminance(hex_color):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def letter_color(bg):
    """White letter on dark/saturated colors, near-black on light ones (yellow, white...)."""
    return "#FFFFFF" if 1.05 / (_luminance(bg) + 0.05) >= 2.6 else "#1C1917"


def auto_color(app_name):
    return COLORS[sum(map(ord, app_name)) % len(COLORS)]


def _png_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


def make_icon_set(src_path, app_name, log=print, color=None):
    """Return {size: png_bytes}. Uses Windows' System.Drawing when available.
    color: '#RRGGBB' for the generated icon, or None/'auto' to pick one from the name."""
    letter = next((ch.upper() for ch in app_name if ch.isalnum()), "A")
    if src_path and src_path.lower().endswith(".svg"):
        log("SVG icons aren't supported yet - using a generated icon instead.")
        src_path = None
    if os.name == "nt":
        out = tempfile.mkdtemp(prefix="chimipack_icon_")
        c1 = color if (color and re.fullmatch(r"#[0-9a-fA-F]{6}", color)) else auto_color(app_name)
        env = dict(os.environ, CHIMI_SRC=src_path or "", CHIMI_OUT=out, CHIMI_LETTER=letter,
                   CHIMI_C1=c1, CHIMI_FG=letter_color(c1), CHIMI_SIZES=",".join(map(str, SIZES)),
                   CHIMI_IOS_SIZES=",".join(map(str, IOS_SIZES)))
        script = os.path.join(out, "icon.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(_PS_SCRIPT)
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
                           env=env, capture_output=True, text=True, creationflags=0x08000000)
        result = {}
        for s in SIZES:
            p = os.path.join(out, f"icon_{s}.png")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    result[s] = f.read()
        for s in IOS_SIZES:
            p = os.path.join(out, f"ios_{s}.png")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    result[f"ios{s}"] = f.read()
        if all(s in result for s in SIZES):
            return result
        log("Icon conversion failed: " + (r.stderr.strip()[:300] or "unknown error") + " - using source as-is.")
    # Fallback: use the PNG directly for every size.
    if src_path and src_path.lower().endswith(".png"):
        with open(src_path, "rb") as f:
            data = f.read()
        result = {s: data for s in SIZES}
        result.update({f"ios{s}": data for s in IOS_SIZES})
        return result
    return {}


def build_ico(icon_set):
    sizes = [s for s in (16, 24, 32, 48, 64, 128, 256) if s in icon_set]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries, blobs = b"", b""
    offset = 6 + 16 * len(sizes)
    for s in sizes:
        data = icon_set[s]
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs
