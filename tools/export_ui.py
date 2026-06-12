"""Export the UI / system text (floppy SYSTEM.TOS, SYSTEM2.TOS, FSYS.TOS) to TSVs
for translation, mirroring tools/export_script.py for dialogue.

Each NUL-separated record becomes one row:
  block_off  the .TOS file name (e.g. SYSTEM.TOS)
  str_off    record offset inside the file (hex)
  speaker    always empty (kept for a uniform 5-column schema with the script TSVs)
  text       the record rendered as markup (glodia.uitext.decode_markup)
  english    translator fills this in; re-encoded by tools/patch_ui.py

Only clean, text-bearing records are exported (the file-header record and any
non-text/binary records are skipped). Existing `english` is preserved on re-export.

Usage: python tools/export_ui.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import D88
from glodia.uitext import decode_markup, encode_markup
from extract_floppy import read_file

JP_D88 = next(p for p in ROOT.glob("*.D88")
              if "SystemDisk" in p.name and "_EN" not in p.name)
FILES = ["SYSTEM.TOS", "SYSTEM2.TOS", "FSYS.TOS"]
OUT = ROOT / "script"
CJK = lambda s: any("ぁ" <= c <= "ん" or "ァ" <= c <= "ヶ" or "一" <= c <= "鿿" for c in s)


def records(data):
    """Yield (offset, raw_bytes) for every NUL-separated record."""
    off = 0
    for r in data.split(b"\x00"):
        yield off, r
        off += len(r) + 1


def translatable(off, r):
    if off == 0 or not r:                       # header / empty
        return False
    mk = decode_markup(r)
    if "?" in mk:                               # undecodable bytes -> not text
        return False
    if encode_markup(mk) != r:                  # must round-trip exactly
        return False
    return CJK(mk)


def main():
    fs = D88(JP_D88.read_bytes())
    for fname in FILES:
        data = read_file(fs, fname)
        path = OUT / (fname.replace(".", "_") + ".tsv")
        existing = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines()[1:]:
                c = line.split("\t")
                if len(c) >= 5 and c[4].strip():
                    existing[(c[0], c[1])] = c[4]
        n = 0
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("block_off\tstr_off\tspeaker\ttext\tenglish\n")
            for off, r in records(data):
                if not translatable(off, r):
                    continue
                bo, so = fname, f"{off:#x}"
                eng = existing.get((bo, so), "")
                f.write(f"{bo}\t{so}\t\t{decode_markup(r)}\t{eng}\n")
                n += 1
        print(f"{fname:12s} {n:4d} records -> {path.name}")


if __name__ == "__main__":
    main()
