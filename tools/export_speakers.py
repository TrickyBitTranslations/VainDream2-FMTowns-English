"""Export the literal-katakana dialogue speaker labels to script/SPEAKERS.tsv.

A one-off field NPC's name is stored as literal katakana framed by event
separators -- ``FF <kana-name> FF`` -- in the dlz block's event stream, right
before that NPC's dialogue record. (Recurring characters use ``⟨02 nn⟩`` NAME.P
*tokens* instead, which patch_names already translates.) These literal-kana
labels were never extracted -- they're short and live in the event bytes -- so
the classifier patch renders their raw kana as Latin mojibake ("ケイ" -> "wF").

This scanner is record-ANCHORED: it only accepts a ``FF <kana> FF`` that sits
immediately before a real dialogue record (found by the same extractor the
script export uses), which excludes event-data byte coincidences. Output is one
row per unique kana name, with an occurrence count and a sample line for
context; the translator fills `english`, and tools/reinsert.py swaps the kana
for the English in the event stream when it rebuilds each block.

Usage: python tools/export_speakers.py
"""
import pathlib, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from glodia import disc, dlz, kana
from glodia.script import load_names, extract_strings

TRACK1_SECTORS = 2715
OUT = ROOT / "script" / "SPEAKERS.tsv"


def _is_kataname(s):
    return s and all(("ァ" <= c <= "ヶ") or c in "ー・　" for c in s)


def find_labels(block, names_tbl):
    """Yield (kana_name, sample_text) for each FF<kana>FF immediately before a
    real dialogue record in this block."""
    for off, _speaker, text in extract_strings(block, names_tbl):
        if off < 2 or block[off - 1] != 0xFF:        # record not FF-preceded
            continue
        j = off - 2
        while j >= 0 and block[j] != 0xFF:            # back to the opening FF
            j -= 1
        if j < 0:
            continue
        raw = block[j + 1:off - 1]
        if not (1 <= len(raw) <= 12):
            continue
        nm = kana.decode(raw)
        if _is_kataname(nm):
            yield nm, text


def main():
    data_bin = (ROOT / "floppy_files" / "DATA.BIN").read_bytes()
    names_tbl = load_names(data_bin)
    iso = disc.extract_track1_iso(str(ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"),
                                  TRACK1_SECTORS)
    count = defaultdict(int)
    sample = {}
    for name in sorted(disc.list_files(iso)):
        if not name.endswith((".DAT", ".PK")):
            continue
        data = disc.read_file(iso, name)
        for pos, m in dlz.iter_members(data):
            try:
                block = dlz.decode_block(m)
            except ValueError:
                continue
            if block[:4] == b"PICT":
                continue
            for nm, text in find_labels(block, names_tbl):
                count[nm] += 1
                sample.setdefault(nm, text.replace("\n", " ")[:30])

    existing = {}
    if OUT.exists():
        for c in tsv.rows(OUT):
            if len(c) >= 4 and c[3].strip():
                existing[c[0]] = c[3]

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("kana\tcount\tsample\tenglish\n")
        for nm in sorted(count, key=lambda k: (-count[k], k)):
            f.write(f"{nm}\t{count[nm]}\t{sample[nm]}\t{existing.get(nm, '')}\n")
    print(f"wrote {len(count)} unique speaker labels -> {OUT.name}")


if __name__ == "__main__":
    main()
