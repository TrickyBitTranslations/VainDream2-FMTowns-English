"""Export the "block pack": everything the translation checker needs, without
the game dump - so contributors and CI can validate script/*.tsv standalone.

Contents (script/blockpack.json.gz, committed):
  blocks[archive][block_off] = { size: compressed member byte budget,
                                 data: base64 decompressed block }
  tokens[EN_NAME] = token id          ({NAME} syntax)
  names[token id] = English name      (rendered-width estimation)

Covers every block referenced by any row in script/*.tsv. Regenerate (needs
the dump) whenever the script export or name romanizations change:
    python tools/make_blockpack.py

Usage: python tools/make_blockpack.py
"""
import base64, gzip, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from glodia import disc, dlz
from glodia.script import load_names
import patch_names

TRACK1_SECTORS = 2715
OUT = ROOT / "script" / "blockpack.json.gz"


def main():
    iso = disc.extract_track1_iso(str(ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"),
                                  TRACK1_SECTORS)
    wanted = {}                                  # archive -> set of block_offs
    for tsv in sorted((ROOT / "script").glob("*.tsv")):
        # Only dialogue TSVs are dlz CD blocks (NAMES.tsv, *_TOS.tsv are not).
        if not (tsv.stem.endswith("_DAT") or tsv.stem.endswith("_PK")):
            continue
        archive = tsv.stem.replace("_DAT", ".DAT").replace("_PK", ".PK")
        for cols in tsv.rows(tsv):
            if len(cols) >= 2:
                wanted.setdefault(archive, set()).add(int(cols[0], 16))

    blocks = {}
    n = 0
    for archive, offs in sorted(wanted.items()):
        data = disc.read_file(iso, archive)
        members = dict(dlz.iter_members(data))
        blocks[archive] = {}
        for off in sorted(offs):
            m = members[off]
            block = dlz.decode_block(m)
            blocks[archive][f"{off:#x}"] = {
                "size": len(m),
                "data": base64.b64encode(block).decode(),
            }
            n += 1

    jp_names = load_names((ROOT / "floppy_files" / "DATA.BIN").read_bytes())
    tokens = {}
    names = {}
    for tok, jp in jp_names.items():
        if jp in patch_names.TRANSLATIONS:
            en = patch_names.TRANSLATIONS[jp]
            tokens[en.upper()] = tok
            names[str(tok)] = en

    # only carry records that are structurally valid name/phrase text - the
    # NUL-split past the real end of NAME.P wanders into binary data
    def sane_record(raw):
        if not raw or len(raw) > 30:
            return False
        i = 0
        while i < len(raw):
            b = raw[i]
            if b in (0x04,) or 0x14 <= b <= 0x20:
                i += 1
            elif 0x21 <= b <= 0x4F:                  # kanji pair
                if i + 1 >= len(raw) or not (0x21 <= raw[i + 1] <= 0x7E):
                    return False
                i += 2
            elif 0x50 <= b <= 0xFF:                  # digit/kana
                i += 1
            else:
                return False
        return True

    from glodia.script import load_names as _ln  # records incl. raw bytes
    data_bin = (ROOT / "floppy_files" / "DATA.BIN").read_bytes()
    raw_recs = data_bin[4123 + 8:].split(b"\x00")
    jp_clean = {t: jp for t, jp in jp_names.items()
                if t - 1 < len(raw_recs) and sane_record(raw_recs[t - 1])}

    pack = {"blocks": blocks, "tokens": tokens, "names": names,
            "jp_names": {str(t): jp for t, jp in jp_clean.items()},
            # raw record byte lengths for EVERY slot up to the last sane one
            # (empty records count in token indexing): CI name-budget checks
            "jp_lens": {str(t): len(raw_recs[t - 1])
                        for t in range(1, max(jp_clean) + 1)}}
    OUT.write_bytes(gzip.compress(json.dumps(pack).encode(), mtime=0))
    print(f"wrote {OUT.relative_to(ROOT)}: {n} blocks across {len(blocks)} archives, "
          f"{len(tokens)} name tokens ({OUT.stat().st_size >> 10} KB)")


if __name__ == "__main__":
    main()
