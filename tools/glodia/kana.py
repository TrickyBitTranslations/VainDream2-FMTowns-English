"""Glodia (Vain Dream II) custom text codec.

The text dispatcher (MAIN.EXP @0x44f0 / @0x4877) classifies each byte:

    byte        meaning
    ----------  --------------------------------------------------------------
    0x00        record/space separator
    0x1e        ー (long-vowel mark)
    < 0x20      control / formatting code (newline, name-token, color, wait, …)
    0x20        space
    0x21-0x4f   KANJI lead byte → 2-byte raw JIS X 0208 (lead,trail), JIS = (b, b2)
                (Glodia uses only JIS level-1 kanji, rows 0x30-0x4f, so lead < 0x50
                 cleanly distinguishes 2-byte kanji from 1-byte kana.)
    0x50-0x59   full-width digit/symbol → JIS row 0x23, cell = byte - 0x20  (０-９)
    0x5a-0xac   HIRAGANA  → JIS row 0x24, JIS = 0x2421 + (byte - 0x5a)
    0xad-0xff   KATAKANA  → JIS row 0x25, JIS = 0x2521 + (byte - 0xad)

Verified end-to-end: NAME.P names (ウォーリック/レイナ/ファーニス/ブージ…), the place list, and
real dialogue words decoded from VAIN_*.DAT members (確かに, それで, 似ている, 久しぶり, …).
"""

KATAKANA_BASE = 0xAC  # legacy alias; katakana = 0xad..0xff (cell = code - 0xac)


def _jis_char(row, lo):
    try:
        return bytes([row | 0x80, lo | 0x80]).decode("euc-jp")
    except UnicodeDecodeError:
        return None


def _katakana(code):
    """Map a katakana code (0xad-0xff) to its character, or None. (Back-compat helper.)"""
    if not (0xAD <= code <= 0xFF):
        return None
    return _jis_char(0x25, 0x21 + (code - 0xAD))


def decode(data, control="⟨{:02x}⟩", unknown="[{:02x}]"):
    """Decode a Glodia text span to Unicode.

    `control` formats control bytes (< 0x20, except 0x1e); pass control="" to drop them.
    """
    out = []
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        if b == 0x1E:
            out.append("ー"); i += 1
        elif b == 0x00:
            out.append("\x00"); i += 1
        elif b < 0x20:
            out.append(control.format(b)); i += 1
        elif b == 0x20:
            out.append(" "); i += 1
        elif b <= 0x4F:                       # 2-byte kanji (raw JIS, level-1)
            if i + 1 < n:
                c = _jis_char(b, data[i + 1])
                out.append(c if c else unknown.format(b) + unknown.format(data[i + 1]))
                i += 2
            else:
                out.append(unknown.format(b)); i += 1
        elif b <= 0x59:                       # full-width digit/symbol, row 0x23
            c = _jis_char(0x23, b - 0x20)
            out.append(c if c else unknown.format(b)); i += 1
        elif b <= 0xAC:                       # hiragana, row 0x24
            c = _jis_char(0x24, 0x21 + (b - 0x5A))
            out.append(c if c else unknown.format(b)); i += 1
        else:                                 # katakana, row 0x25
            c = _jis_char(0x25, 0x21 + (b - 0xAD))
            out.append(c if c else unknown.format(b)); i += 1
    return "".join(out)


def encode(text):
    """Encode a Unicode string to Glodia text bytes (inverse of decode()).

    Handles emdash, spaces, hiragana, katakana, full-width digits, and JIS level-1
    kanji/punctuation (rows < 0x50). Raises ValueError on anything else -
    control codes must be emitted by the caller.
    """
    out = bytearray()
    for ch in text:
        if ch == "ー":
            out.append(0x1E)
            continue
        if ch in (" ", "　"):
            out.append(0x20)
            continue
        try:
            hi, lo = ch.encode("euc-jp")
        except (UnicodeEncodeError, ValueError):
            raise ValueError(f"unencodable: {ch!r}")
        row, cell = hi & 0x7F, lo & 0x7F
        if row == 0x24:                               # hiragana
            out.append(0x5A + (cell - 0x21))
        elif row == 0x25:                             # katakana
            out.append(0xAD + (cell - 0x21))
        elif row == 0x23 and 0x30 <= cell <= 0x39:    # full-width digit
            out.append(0x50 + (cell - 0x30))
        elif row < 0x50:                              # kanji/punct: raw 2-byte JIS
            out += bytes([row, cell])
        else:
            raise ValueError(f"unencodable: {ch!r} (JIS row {row:#x})")
    return bytes(out)


def split_records(data):
    """Split a 0x00-separated text blob (e.g. NAME.P body) into records."""
    return [r for r in data.split(b"\x00") if r]
