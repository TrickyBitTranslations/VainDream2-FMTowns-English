"""Export the NAME.P name/term table to script/NAMES.tsv for translation.

NAME.P (in DATA.BIN) holds the character/place/term names and the menu phrases the
dialogue inserts via {NAME} tokens. This is the *source* the build reads
(patch_names.TRANSLATIONS is loaded from this TSV), and it feeds the {NAME} token
map and the site's Names tab.

One row per non-empty NAME.P record:
  block_off  always "NAME.P"
  str_off    the 1-based token number (hex) -- the {NAME} insert index
  speaker    empty (uniform 5-column schema)
  text       the original Japanese (read-only)
  english    the translation

Existing `english` is preserved on re-export. The very first run seeds english
from the legacy patch_names.TRANSLATIONS dict if it's still a literal.

Usage: python tools/export_names.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from glodia.script import _decode_record
from extract_floppy import read_file

JP_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88"
TABLE_OFF = 4123 + 8                     # NAME.P body, after the 8-byte header
TSV = ROOT / "script" / "NAMES.tsv"


def records():
    data = read_file(read_d88(JP_D88.read_bytes()), "DATA.BIN")
    for i, r in enumerate(data[TABLE_OFF:].split(b"\x00")):
        yield i + 1, r                   # 1-based token number


def main(seed=None):
    # preserve existing english; optionally seed from a {jp: en} dict (migration)
    existing = {}
    if TSV.exists():
        for line in TSV.read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 5 and c[4].strip():
                existing[c[1]] = c[4]
    n = 0
    with open(TSV, "w", encoding="utf-8", newline="\n") as f:
        f.write("block_off\tstr_off\tspeaker\ttext\tenglish\n")
        for tok, r in records():
            if not r:
                continue
            jp = _decode_record(r)
            so = f"{tok:#x}"
            eng = existing.get(so) or (seed or {}).get(jp, "")
            f.write(f"NAME.P\t{so}\t\t{jp}\t{eng}\n")
            n += 1
    print(f"NAME.P {n} records -> {TSV.name}")


if __name__ == "__main__":
    main()
