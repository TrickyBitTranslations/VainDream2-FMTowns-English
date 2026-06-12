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


def check():
    """Validate that every translated UI record re-encodes; returns error count."""
    tr = load_translations()
    errors = 0
    for (fname, so), eng in sorted(tr.items()):
        try:
            encode_markup(eng)
        except Exception as e:
            print(f"ERROR {fname} {so}: {e}  [{eng!r}]")
            errors += 1
    print(f"{len(tr)} translated UI records validated; {errors} error(s)")
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
    for f in FILES:
        orig = read_file(jp_fs, f)
        print(f"  {f:12s} {len(orig):5d} -> {len(blobs[f]):5d} B")
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
