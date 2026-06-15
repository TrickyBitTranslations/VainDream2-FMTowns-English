"""Translate NAME.P records (names/terms for ⟨02 nn⟩ inserts + speaker titles).

The lookup (MAIN.EXP @0x42b6) scans NUL separators, so record lengths are free as long
as the count/order is unchanged and the total span length stays exact (binary data
follows the table in DATA.BIN). Slack comes from shrinking the 未使用 ("unused")
placeholders and padding the last with ⟨04⟩.

Patches the classifier-patched floppy in place (run patch_main_exp.py first);
translations are 1-byte ASCII and need that patch to render.

Usage: python tools/patch_main_exp.py && python tools/patch_names.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from glodia.floppy import read_d88
from glodia.script import _decode_record
from glodia.english import encode as en

EN_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
TABLE_OFF = 4123 + 8       # NAME.P body inside DATA.BIN (after "NAME.P" header)

# Translations come from script/NAMES.tsv (see export_names.py), keyed by the
# original decoded Japanese (matches the NAME.P records and the {NAME} token map).
NAMES_TSV = ROOT / "script" / "NAMES.tsv"


def _load_translations():
    out = {}
    for c in tsv.rows(NAMES_TSV):
        if len(c) >= 5 and c[4].strip():
            out[c[3]] = c[4]
    return out


TRANSLATIONS = _load_translations()
PAD_RECORD = "未使用"       # last placeholder absorbs the remaining slack


def _translated(d):
    # "X" marks a record that isn't a real name (grammar glue etc.) - keep its
    # original Japanese, don't encode the X.
    return d in TRANSLATIONS and d != PAD_RECORD and TRANSLATIONS[d] != "X"


def read_file_from(fs, name):
    from extract_floppy import read_file
    return read_file(fs, name)


# the playable cast - always keep these even if no dialogue references them yet
CAST = {"ウォーリック", "レイナ", "ファーニス", "ブージ", "ダ　ン", "ランバート", "大婆様",
        "セシリア", "ブラフォード", "セス", "ナッツ", "ライド", "キャロル", "ベイグ"}


def _protected_indices(decoded):
    """Record indices that must NOT be dropped: names referenced by a {NAME}
    token in any dialogue translation, plus the cast."""
    import re
    import reinsert
    tokens = reinsert.name_token_map()                 # EN(upper) -> token id
    referenced_tokens = set()
    for tsv_path in (ROOT / "script").glob("*.tsv"):
        for cols in tsv.rows(tsv_path):
            if len(cols) >= 5 and cols[4].strip():
                for ref in re.findall(r"\{([^}]+)\}", cols[4]):
                    tok = tokens.get(ref.upper())
                    if tok is not None:
                        referenced_tokens.add(tok)
    protected = {tok - 1 for tok in referenced_tokens}  # token is 1-based
    protected |= {i for i, d in enumerate(decoded) if d in CAST}
    return protected


JP_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88"


def full_name_table():
    """The COMPLETE NAME.P table - every record translated, NO budget cull - for
    loading into the carved segment (which escapes DATA.BIN's RAM-bounded cap).
    Reads the ORIGINAL Japanese DATA.BIN (so records decode to JP and map via
    TRANSLATIONS). Returns b'NAME.P\\x01.' + the NUL-joined records."""
    data_bin = read_file_from(read_d88(JP_D88.read_bytes()), "DATA.BIN")
    recs = data_bin[TABLE_OFF:].split(b"\x00")
    decoded = [_decode_record(r) for r in recs]
    out = [en(TRANSLATIONS[d]) if _translated(d)
           else (b"" if d == PAD_RECORD else r)
           for d, r in zip(decoded, recs)]
    return data_bin[TABLE_OFF - 8:TABLE_OFF] + b"\x00".join(out)   # "NAME.P\x01." + records


def main():
    fs = read_d88(EN_D88.read_bytes())
    data_bin = read_file_from(fs, "DATA.BIN")

    # The whole region from TABLE_OFF to EOF is ONE NUL-separated table; the
    # engine looks records up by counting NULs (position-independent), so record
    # LENGTHS are free. BUT DATA.BIN is read by absolute disk sector - it can't
    # move or gain a cluster - so the table must fit DATA.BIN's capacity. If the
    # full set overflows, drop the costliest (biggest English-over-Japanese)
    # translations until it fits.
    recs = data_bin[TABLE_OFF:].split(b"\x00")
    decoded = [_decode_record(r) for r in recs]
    # DATA.BIN can't move (read by absolute sector), but the game reads its full
    # 6-sector cluster allocation (6144B) regardless of the directory size, so the
    # table may use all of it - not just the original 6085 bytes.
    cap = fs.file_capacity("DATA.BIN")
    chosen = {i for i, d in enumerate(decoded) if _translated(d)}
    pad_idx = max(i for i, d in enumerate(decoded) if d == PAD_RECORD)

    # PROTECT names players actually see: any name referenced by a {NAME} token in
    # a dialogue translation (else that line renders the Japanese name as garble),
    # plus the playable cast. The auto-fit drops unprotected names first.
    protected = _protected_indices(decoded)

    def body(sel, pad=0):
        # empty ALL unused placeholder records (reclaims their bytes); translate
        # chosen; keep the rest. The pad record then absorbs the exact slack.
        out = [en(TRANSLATIONS[decoded[i]]) if i in sel
               else (b"" if decoded[i] == PAD_RECORD else r)
               for i, r in enumerate(recs)]
        out[pad_idx] = b"\x04" * pad
        return data_bin[:TABLE_OFF] + b"\x00".join(out)

    def overage(i):
        return len(en(TRANSLATIONS[decoded[i]])) - len(recs[i])

    dropped = []
    while len(body(chosen)) > cap and chosen:
        # drop the costliest UNPROTECTED name; only touch protected if forced
        pool = [i for i in chosen if i not in protected] or list(chosen)
        worst = max(pool, key=overage)
        chosen.discard(worst)
        dropped.append(decoded[worst])
    # pad the placeholder so DATA.BIN is exactly its original size
    new_data_bin = body(chosen, cap - len(body(chosen)))
    assert len(new_data_bin) == cap
    img = fs.grow_file("DATA.BIN", new_data_bin)
    EN_D88.write_bytes(img)

    fs2 = read_d88(EN_D88.read_bytes())
    from glodia.english import decode as en_dec
    check = read_file_from(fs2, "DATA.BIN")[TABLE_OFF:].split(b"\x00")
    print(f"name table: {len(chosen)} of {len(chosen)+len(dropped)} names translated "
          f"(DATA.BIN held at {cap} bytes - read by absolute sector, can't grow)")
    if dropped:
        print(f"  {len(dropped)} didn't fit (kept Japanese): {', '.join(dropped[:14])}"
              + (" ..." if len(dropped) > 14 else ""))
    for i in sorted(chosen)[:5]:
        print(f"  token {i+1:#04x}: {decoded[i]!r} -> {en_dec(check[i])!r}")


if __name__ == "__main__":
    main()
