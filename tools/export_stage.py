"""Export the STAGE place/location table to script/STAGE.tsv.

The save/load screen shows the save LOCATION from this table (e.g. Warrick's
House). It's a member of VAIN_S.DAT (offset 0x6656b), dlz-compressed, decompressed
to DATA:0x1800. Records are NUL-separated place names in the dialogue codec:
raw-JIS text with {NAME} inserts (the ⟨02 nn⟩ token) and <14> column spacers.

Usage: python tools/export_stage.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from glodia import disc, dlz
from glodia.kana import decode as kana_decode
import reinsert

ARCHIVE = "VAIN_S.DAT"
MEMBER = 0x6656B
IMG = ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"
OUT = ROOT / "script" / "STAGE.tsv"
TRACK1 = 2715

_GLYPH = {0x15: "、", 0x16: "。", 0x1c: "？", 0x1d: "！"}
CJK = lambda s: any("ぁ" <= c <= "ん" or "ァ" <= c <= "ヶ" or "一" <= c <= "鿿" for c in s)


def _id_to_token():
    return {v: k for k, v in reinsert.name_token_map().items()}   # id -> EN name


def decode_record(r, id2tok):
    out, i, n = [], 0, len(r)
    while i < n:
        b = r[i]
        if b == 0x02 and i + 1 < n:                       # name insert
            nn = r[i + 1]; tok = id2tok.get(nn)
            out.append("{" + tok + "}" if tok else f"{{{nn:02x}}}"); i += 2
        elif b == 0x14:
            out.append("<14>"); i += 1
        elif b == 0x19:
            out.append("/"); i += 1
        elif b == 0x1e:
            out.append("~"); i += 1
        elif b in _GLYPH:
            out.append(_GLYPH[b]); i += 1
        elif b < 0x21:
            out.append(f"<{b:02x}>"); i += 1
        elif b <= 0x4f and i + 1 < n:                      # 2-byte kanji
            out.append(kana_decode(r[i:i + 2], unknown="?")); i += 2
        else:
            out.append(kana_decode(r[i:i + 1], unknown="?")); i += 1
    return "".join(out)


def stage_records():
    """(member_bytes, [raw record]) for the STAGE table in VAIN_S.DAT."""
    iso = disc.extract_track1_iso(str(IMG), TRACK1)
    members = dict(dlz.iter_members(disc.read_file(iso, ARCHIVE)))
    dec = dlz.decode_block(members[MEMBER])
    assert dec[:6] == b"STAGE.", dec[:8]
    return dec, dec[8:].split(b"\x00")


def main():
    dec, recs = stage_records()
    id2 = _id_to_token()
    existing = {}
    if OUT.exists():
        for c in tsv.rows(OUT):
            if len(c) >= 5 and c[4].strip():
                existing[c[1]] = c[4]
    n = 0
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("block_off\tstr_off\tspeaker\ttext\tenglish\n")
        for idx, r in enumerate(recs):
            if not r:
                continue
            text = decode_record(r, id2)
            if not CJK(text):                # tokens-only / binary -> not translatable
                continue
            so = f"{idx:#x}"
            f.write(f"STAGE\t{so}\t\t{text}\t{existing.get(so, '')}\n")
            n += 1
    print(f"STAGE: {n} place records -> {OUT.name}  (member decomp {len(dec)}B / 2048 cap)")


if __name__ == "__main__":
    main()
