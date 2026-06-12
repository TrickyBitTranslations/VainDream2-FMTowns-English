"""Reinsert translated UI / system text into the floppy .TOS files.

Reads the translations from script/SYSTEM_TOS.tsv, script/SYSTEM2_TOS.tsv,
script/FSYS_TOS.tsv (produced by tools/export_ui.py), re-encodes each translated
record with glodia.uitext.encode_markup, and writes the rebuilt .TOS files into
the EN floppy via floppy.extend_file (same whole-file DOS loader path as ITEM.TOS).

Untranslated records pass through byte-for-byte, so with no translations the
output file is identical to the original.

Usage: python tools/patch_ui.py          # dry run (reports sizes)
       python tools/patch_ui.py --write   # write into the EN floppy
       (or call patch_ui.main(write=True) from the build)
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from glodia.uitext import encode_markup
from extract_floppy import read_file

# Fixed paths (resolved lazily in main()): importing this module must NOT touch
# the filesystem -- the site build (make_site_data -> grow_build) imports it on CI
# where the game data is absent.
JP_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88"
EN_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
FILES = ["SYSTEM.TOS", "SYSTEM2.TOS", "FSYS.TOS"]

# Each .TOS loads into a FIXED RAM slot (loader table @MAIN.EXP ~0x2140); growing a
# file past its slot overruns the next struct and crashes. Caps verified live in the
# emulator (see docs/findings/2026-06-12-tos-fixed-buffers-need-relocation.md):
#   SYSTEM.TOS  DATA:0xC400 -> scene buffer 0xCC00      = 2048 (hard)
#   FSYS.TOS    0x114:0x1400 -> next PICT, free to 0x19C0 (conservative)
#   SYSTEM2.TOS 0x114:0xD800 -> free to ~0xDB10         (conservative)
TOS_CAP = {"SYSTEM.TOS": 2048, "FSYS.TOS": 1472, "SYSTEM2.TOS": 784}


def load_translations():
    """{(file, str_off): english_markup} from the UI TSVs."""
    tr = {}
    for fname in FILES:
        path = ROOT / "script" / (fname.replace(".", "_") + ".tsv")
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 5 and c[4].strip():
                tr[(c[0], c[1])] = c[4]
    return tr


def rebuild(jp_fs, fname, tr):
    """Reassemble a .TOS: translated records re-encoded, the rest verbatim."""
    data = read_file(jp_fs, fname)
    out, off = [], 0
    for r in data.split(b"\x00"):
        eng = tr.get((fname, f"{off:#x}"))
        out.append(encode_markup(eng) if eng else r)
        off += len(r) + 1
    return b"\x00".join(out)


import re as _re


def _vis_cells(markup):
    """Rendered width per column-segment: visible glyph cells. Only <14> (column
    spacer) and \\n break; <04> is a half-space (counts), <03:nn>/other <nn> render
    nothing."""
    s = _re.sub(r"<03:[0-9a-fA-F]{2}>", "", markup)         # format op: 0 cells
    s = s.replace("<04>", " ")                              # half-space: 1 cell
    s = _re.sub(r"<14>|\\n", "\x01", s)                     # column spacer / newline: break
    s = _re.sub(r"<[0-9a-fA-F]{2}>", "", s)                 # other control: 0 cells
    return [len(seg) for seg in s.split("\x01")]


def check(rows=None):
    """Validate every translated UI record re-encodes; returns error count.
    Box-fit heuristic: warn when English renders wider than the Japanese it
    replaces (the fixed menu layout assumes the original widths)."""
    tr = load_translations()
    jp = {}                                                 # (file, off) -> jp markup
    for fname in FILES:
        path = ROOT / "script" / (fname.replace(".", "_") + ".tsv")
        if path.exists():
            for ln in path.read_text(encoding="utf-8").splitlines()[1:]:
                c = ln.split("\t")
                if len(c) >= 4:
                    jp[(fname, c[1])] = c[3]
    errors = warns = 0
    for (fname, so), eng in sorted(tr.items()):
        try:
            encode_markup(eng)
        except Exception as e:
            print(f"ERROR {fname} {so}: {e}  [{eng!r}]")
            errors += 1
            continue
        en_w, jp_w = max(_vis_cells(eng), default=0), max(_vis_cells(jp.get((fname, so), "")), default=0)
        if en_w > jp_w + 1:
            print(f"WARN  {fname} {so}: renders {en_w} cells vs {jp_w} in JP — may overflow its menu column")
            warns += 1
    print(f"{len(tr)} translated UI records validated; {errors} error(s), {warns} warning(s)")
    return errors


def main(write=False):
    if "--check" in sys.argv:
        sys.exit(1 if check() else 0)
    if "--write" in sys.argv:
        write = True
    jp_fs = read_d88(JP_D88.read_bytes())
    tr = load_translations()
    n_tr = len(tr)
    blobs = {f: rebuild(jp_fs, f, tr) for f in FILES}
    over = []
    for f in FILES:
        orig = read_file(jp_fs, f)
        cap = TOS_CAP[f]
        flag = "" if len(blobs[f]) <= cap else f"  *** OVER CAP {cap} ***"
        print(f"  {f:12s} {len(orig):5d} -> {len(blobs[f]):5d} / {cap} B{flag}")
        if len(blobs[f]) > cap:
            over.append((f, len(blobs[f]), cap))
    if over:
        raise SystemExit(
            "UI .TOS over its fixed RAM slot (would overrun the next struct and crash):\n  "
            + "\n  ".join(f"{f}: {n} > {cap} B — shorten translations for this file"
                          for f, n, cap in over))
    if not write:
        print(f"(dry run; {n_tr} translated records) -- pass --write to apply")
        return
    img = EN_D88.read_bytes()
    fs = read_d88(img)
    for f in FILES:
        img = fs.extend_file(f, blobs[f])
        fs = read_d88(img)
    EN_D88.write_bytes(img)
    print(f"wrote {n_tr} translated UI records into {EN_D88.name}")


if __name__ == "__main__":
    main()
