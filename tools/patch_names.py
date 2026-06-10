"""Translate NAME.P records (names/terms used by ⟨02 nn⟩ inserts + speaker titles).

The engine lookup (MAIN.EXP @0x42b6) scans NUL separators, so record LENGTHS are
free as long as (a) the record count/order is unchanged and (b) the total byte
length of the rewritten span stays exact (binary data follows the table inside
DATA.BIN). Shortfall is absorbed by shrinking the 未使用 ("unused") placeholder
records and padding the last one with ⟨04⟩.

Operates on the classifier-patched floppy IN PLACE (run patch_main_exp.py first):
translations are 1-byte ASCII (glodia/english.py) and need that patch to render.

Usage: python tools/patch_main_exp.py && python tools/patch_names.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from glodia.script import _decode_record
from glodia.english import encode as en

EN_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
TABLE_OFF = 4123 + 8       # NAME.P body inside DATA.BIN (after "NAME.P" header)

# keyd by ORIGINAL decoded text - provisional romanizations, adjust freely
# (sentence case; {NAME} lookups in reinsert.py are case-insensitive)
TRANSLATIONS = {
    "ウォーリック": "Warrick",
    "レイナ": "Reina",
    "ファーニス": "Furnis",
    "ライド": "Ride",
    "セシリア": "Cecilia",
    "ブラフォード": "Blaford",
    "セス": "Seth",
    "ブージ": "Booj",
    "ナッツ": "Nutts",
    "大婆様": "Granny",
    "ダ　ン": "Dan",
    "ランバート": "Lambert",
    "キャロル": "Carol",
    "ベイグ": "Veig",
    "バーナー王子": "Berner",
    "いらっしゃい": "Welcome",
    "へへっ": "Heheh",
    "お兄ちゃん": "Bro",
    "未使用": "X",          # placeholders, shrunk to free budget
}
PAD_RECORD = "未使用"       # last placeholder absorbs the remaining slack


def read_file_from(fs, name):
    from extract_floppy import read_file
    return read_file(fs, name)


def main():
    image = EN_D88.read_bytes()
    fs = read_d88(image)
    data_bin = read_file_from(fs, "DATA.BIN")
    recs = data_bin[TABLE_OFF:].split(b"\x00")

    # rewrite span = records 1..N where N covers the last translated record
    decoded = [_decode_record(r) for r in recs]
    hits = [i for i, d in enumerate(decoded) if d in TRANSLATIONS]
    assert hits, "no translatable records found"
    span_end = max(hits) + 1
    pad_idx = max(i for i in hits if decoded[i] == PAD_RECORD)

    orig_span = recs[:span_end]
    orig_len = sum(len(r) for r in orig_span) + span_end   # records + NULs
    new = list(orig_span)
    for i in hits:
        new[i] = en(TRANSLATIONS[decoded[i]])
    new_len = sum(len(r) for r in new) + span_end
    slack = orig_len - new_len
    if slack < 0:
        raise SystemExit(f"translations {-slack} bytes over budget - shorten some")
    new[pad_idx] += b"\x04" * slack
    rebuilt = b"\x00".join(new) + b"\x00"
    assert len(rebuilt) == orig_len

    # write in contiguous flat-space runs (file may be cluster-fragmented)
    run_start = 0
    while run_start < len(rebuilt):
        flat = fs.flat_offset_for_file("DATA.BIN", TABLE_OFF + run_start)
        run_len = 1
        while (run_start + run_len < len(rebuilt) and
               fs.flat_offset_for_file("DATA.BIN", TABLE_OFF + run_start + run_len)
               == flat + run_len):
            run_len += 1
        image = read_d88(image).patch(flat, rebuilt[run_start:run_start + run_len])
        run_start += run_len
    EN_D88.write_bytes(image)

    # verify
    fs2 = read_d88(EN_D88.read_bytes())
    check = read_file_from(fs2, "DATA.BIN")[TABLE_OFF:].split(b"\x00")
    from glodia.english import decode as en_dec
    print(f"rebuilt {span_end} records ({orig_len} bytes, slack {slack} -> pad record)")
    for i in hits[:8] + hits[-3:]:
        print(f"  token {i+1:#04x}: {decoded[i]!r} -> {en_dec(check[i])!r}")


if __name__ == "__main__":
    main()
