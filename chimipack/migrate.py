"""One-time move of data from the tool's old name (before the chimiPack rebrand).

Old locations are spelled out here on purpose; everything else in chimiPack uses the new names.
Runs on import of chimipack.builder, before anything reads settings or the Android signing key,
so an existing key is never replaced by a newly generated one.
"""
import os
import shutil

_HOME = os.path.expanduser("~")
OLD_HOME = os.path.join(_HOME, ".html2app")
NEW_HOME = os.path.join(_HOME, ".chimipack")
# Files that must survive no matter what (the key signs every Android app update).
_ESSENTIAL = ("android-signing-key.json", "settings.json")


def migrate_home():
    if not os.path.isdir(OLD_HOME):
        return
    if not os.path.exists(NEW_HOME):
        try:
            os.rename(OLD_HOME, NEW_HOME)      # fast path: move everything, including the Electron cache
            return
        except OSError:
            os.makedirs(NEW_HOME, exist_ok=True)   # something in the old folder is in use: copy what matters
    for name in _ESSENTIAL:
        src, dst = os.path.join(OLD_HOME, name), os.path.join(NEW_HOME, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
    # Reuse the already-downloaded Electron zip instead of downloading 110 MB again.
    old_e, new_e = os.path.join(OLD_HOME, "electron"), os.path.join(NEW_HOME, "electron")
    if os.path.isdir(old_e):
        os.makedirs(new_e, exist_ok=True)
        for f in os.listdir(old_e):
            src, dst = os.path.join(old_e, f), os.path.join(new_e, f)
            if f.endswith(".zip") and os.path.isfile(src) and not os.path.exists(dst):
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)


migrate_home()
