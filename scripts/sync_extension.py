"""Copy the web app's shared browser modules into the extension.

The extension can't import from the site, so it carries exact copies of:
  vault.js     encryption (must match the site byte for byte, or keys differ)
  fields.js    reading results and the library summary that gets encrypted
  keystore.js  keeping the unlocked key between popup openings

Run after changing any of them:  python scripts/sync_extension.py
tests/web/vault.test.mjs fails if a copy is out of date.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ["vault.js", "fields.js", "keystore.js"]

for name in SHARED:
    src = ROOT / "web" / "assets" / "js" / "lib" / name
    dst = ROOT / "extension" / "lib" / name
    shutil.copyfile(src, dst)
    print(f"copied {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
