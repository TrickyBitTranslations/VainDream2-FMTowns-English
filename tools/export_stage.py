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
from glodia import uitext
import reinsert

ARCHIVE = "VAIN_S.DAT"
MEMBER = 0x6656B
IMG = ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"
OUT = ROOT / "script" / "STAGE.tsv"
TRACK1 = 2715

CJK = lambda s: any("ぁ" <= c <= "ん" or "ァ" <= c <= "ヶ" or "一" <= c <= "鿿" for c in s)


def _id_to_token():
    return {v: k for k, v in reinsert.name_token_map().items()}   # id -> EN name


def decode_record(r, id2tok):
    """Place record -> markup. Shares the .TOS codec, with name tokens (uitext)."""
    return uitext.decode_markup(r, tokens=id2tok)


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
