"""Markup codec for the UI/system .TOS text (SYSTEM.TOS, SYSTEM2.TOS, FSYS.TOS).

Records are NUL-separated, in the game's raw-JIS 1-byte codec (the same grammar
as dialogue, see glodia.script). For the translation TSV we render each record
as a readable markup string (decode_markup) and re-encode the translated English
back to bytes (encode_markup), preserving the layout control codes.

Markup tokens (appear in both the JP `text` column and the `english` column):
  \\n          0x01  newline (next menu row)
  <04>         0x04  cursor-right half-space (Japanese inter-glyph spacing)
  <14>         0x14  layout / column spacer
  <03:nn>      0x03 nn   format op with one arg (color/size/...)
  <nn>         any other lone control byte (0x02, 0x05-0x13, 0x17/18/1a/1b/1f)
  . , ! ? -    map to the game punctuation controls (via glodia.english)
  /            0x19  middle dot  (rendered "・"; use "/" so it stays in the ASCII codec)
  ~            0x1e  long-vowel mark "ー"
  (space)      0x20
  kanji/kana   decoded to Unicode in `text`; the English column is normally ASCII

Angle brackets are written with ASCII < > (not the wide ⟨ ⟩) so the markup itself
stays inside the 1-byte English charset and is easy to type on the website.
"""
import re
from glodia.kana import decode as kana_decode, encode as kana_encode
from glodia.english import encode as en_encode

# control bytes that decode to a visible JP punctuation glyph
_GLYPH = {0x15: "、", 0x16: "。", 0x1c: "？", 0x1d: "！"}
_GLYPH_REV = {v: k for k, v in _GLYPH.items()}
# ASCII stand-ins usable in the English column (kept inside the 1-byte codec)
_MIDDOT = 0x19   # ・  -> "/"
_LONGV = 0x1e    # ー  -> "~"


def decode_markup(data):
    """bytes -> readable markup string (for the TSV `text` column)."""
    out = []
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        if b == 0x01:
            out.append("\\n"); i += 1
        elif b == 0x03 and i + 1 < n:
            out.append(f"<03:{data[i+1]:02x}>"); i += 2
        elif b == 0x04:
            out.append("<04>"); i += 1
        elif b == _MIDDOT:
            out.append("/"); i += 1
        elif b == _LONGV:
            out.append("~"); i += 1
        elif b in _GLYPH:
            out.append(_GLYPH[b]); i += 1
        elif b == 0x20:
            out.append(" "); i += 1
        elif b < 0x21:                       # other lone control (incl 0x14)
            out.append(f"<{b:02x}>"); i += 1
        elif b <= 0x4f and i + 1 < n:        # 2-byte kanji
            out.append(kana_decode(data[i:i + 2], unknown="?")); i += 2
        else:                                # kana / digit
            out.append(kana_decode(data[i:i + 1], unknown="?")); i += 1
    return "".join(out)


_TOK = re.compile(r"<03:([0-9a-fA-F]{2})>|<([0-9a-fA-F]{2})>|\\n")


def encode_markup(s):
    """markup string -> bytes (for reinserting a translated record)."""
    out = bytearray()
    i, n = 0, len(s)
    while i < n:
        m = _TOK.match(s, i)
        if m:
            if m.group(1) is not None:
                out += bytes([0x03, int(m.group(1), 16)])
            elif m.group(2) is not None:
                out.append(int(m.group(2), 16))
            else:                            # \n
                out.append(0x01)
            i = m.end(); continue
        # accumulate a text run up to the next token
        j = i
        while j < n and not (s[j] == "<" and _TOK.match(s, j)) \
                and not (s[j] == "\\" and j + 1 < n and s[j + 1] == "n"):
            j += 1
        out += _encode_text(s[i:j])
        i = j
    return bytes(out)


def _encode_text(run):
    # spaces are LITERAL 0x20 here (UI padding), not the english-codec's 0x04;
    # split on space so en_encode never turns a space into 0x04.
    out = bytearray()
    for k, word in enumerate(run.split(" ")):
        if k:
            out.append(0x20)
        if not word:
            continue
        try:
            out += en_encode(word)           # fast path: ASCII English word
            continue
        except ValueError:
            pass
        for ch in word:
            if ch == "/":
                out.append(_MIDDOT)
            elif ch == "~":
                out.append(_LONGV)
            elif ch == "　":             # ideographic space -> 0x2121
                out += b"\x21\x21"
            elif ch in _GLYPH_REV:           # 、。？！ (round-trip of JP)
                out.append(_GLYPH_REV[ch])
            else:
                try:
                    out += en_encode(ch)
                except ValueError:
                    out += kana_encode(ch)   # leftover JP kana/kanji
    return bytes(out)
