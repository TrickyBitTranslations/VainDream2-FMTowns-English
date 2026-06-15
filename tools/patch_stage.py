"""Reinsert translated place names into the STAGE table (VAIN_S.DAT member 0x6656b).

Reads script/STAGE.tsv (from export_stage.py), re-encodes the translated records,
rebuilds the member, and returns it for grow_build to splice into VAIN_S.DAT and
recompress. Untranslated records pass through byte-for-byte.

The member decompresses to a FIXED RAM slot at DATA:0x1800; the next data (DATA.BIN)
sits at 0x2000, so the decompressed table must stay <= 2048 bytes or it overruns
NAME.P and corrupts. The build guards this.

Usage: python tools/patch_stage.py            # round-trip + budget check
       (or call patch_stage.member_override() from grow_build)
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tsv
from glodia.kana import encode as kana_encode
from glodia.english import encode as en_encode
import reinsert
from export_stage import stage_records, decode_record, _id_to_token, MEMBER

TSV = ROOT / "script" / "STAGE.tsv"
RAM_CAP = 2048                         # DATA:0x1800 .. DATA.BIN @ 0x2000

_GLYPH_REV = {"、": 0x15, "。": 0x16, "？": 0x1c, "！": 0x1d}
_TOK = re.compile(r"\{([^}]+)\}|<([0-9a-fA-F]{2})>")


def encode_record(markup, tokmap):
    """markup string -> STAGE record bytes (inverse of export_stage.decode_record)."""
    out = bytearray()
    i, n = 0, len(markup)
    while i < n:
        m = _TOK.match(markup, i)
        if m:
            if m.group(1) is not None:                 # {NAME} or {hex}
                key = m.group(1)
                tid = tokmap.get(key.upper())
                if tid is None and re.fullmatch(r"[0-9a-fA-F]{2}", key):
                    tid = int(key, 16)
                if tid is None:
                    raise ValueError(f"unknown token {{{key}}}")
                out += bytes([0x02, tid])
            else:                                      # <nn>
                out.append(int(m.group(2), 16))
            i = m.end(); continue
        ch = markup[i]
        if ch == "/":
            out.append(0x19)
        elif ch == "~":
            out.append(0x1e)
        elif ch in _GLYPH_REV:
            out.append(_GLYPH_REV[ch])
        else:
            try:
                out += en_encode(ch)
            except ValueError:
                out += kana_encode(ch)
        i += 1
    return bytes(out)


def _translations():
    tr = {}
    if TSV.exists():
        for c in tsv.rows(TSV):
            if len(c) >= 5 and c[4].strip():
                tr[int(c[1], 16)] = c[4]
    return tr


def member_override():
    """Rebuilt decompressed STAGE member: translated records re-encoded, rest as-is.
    Returns the decompressed bytes (grow_build recompresses + splices)."""
    dec, recs = stage_records()
    tr = _translations()
    tokmap = reinsert.name_token_map()
    out = []
    for idx, r in enumerate(recs):
        eng = tr.get(idx)
        out.append(encode_record(eng, tokmap) if eng else r)
    return dec[:8] + b"\x00".join(out)


def check():
    dec, recs = stage_records()
    id2 = _id_to_token()
    tokmap = reinsert.name_token_map()
    errors = 0
    # 1) original records round-trip (decode -> encode == original). Untranslated
    # records pass through as original bytes, so a record the encoder can't reverse
    # (e.g. ヴ, which decodes but has no encode) is fine - only a true mismatch is a bug.
    for idx, r in enumerate(recs):
        mk = decode_record(r, id2)
        if "?" in mk:                      # has undecodable bytes; skip round-trip
            continue
        try:
            rt = encode_record(mk, tokmap)
        except ValueError:
            continue                       # not encodable; passes through untouched
        if rt != r:
            print(f"ERROR idx {idx:#x}: round-trip mismatch  {mk!r}")
            errors += 1
    # 2) translated member fits the RAM slot
    blob = member_override()
    flag = "" if len(blob) <= RAM_CAP else f"  *** OVER {RAM_CAP} ***"
    print(f"STAGE decompressed: {len(blob)} / {RAM_CAP} B{flag}")
    if len(blob) > RAM_CAP:
        errors += 1
    print(f"{len(recs)} records, {len(_translations())} translated; {errors} error(s)")
    return errors


if __name__ == "__main__":
    sys.exit(1 if check() else 0)
