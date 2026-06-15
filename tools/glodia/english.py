"""1-byte ASCII text codec for the English build (requires the MAIN.EXP
classifier patch: tools/patch_main_exp.py).

The patch remaps the dead kana ranges in the classifier @0x4877 to JIS row 0x23
(full-width alphanumerics; drawn condensed under the ⟨03 03⟩ half-width mode):

    0x5a + k  ->  JIS 0x23:(0x21+k)     (was hiragana; covers ASCII 0x21..0x73)
    0xad + k  ->  JIS 0x23:(0x74+k)     (was katakana; covers ASCII 0x74..0x7e)

Only ASCII with a defined row-0x23 glyph is emitted as a letter byte (digits,
A-Z, a-z). Digits use the untouched native digit class 0x50-0x59. Punctuation
maps to the engine's control punctuation (renders 、。？！・ー), space to ⟨04⟩.
"""

# control-code punctuation (unchanged by the patch)
_PUNCT = {
    " ": 0x04, ".": 0x16, ",": 0x15, "!": 0x1D, "?": 0x1C,
    "-": 0x1E, "・": 0x19, "·": 0x19,      # ・ = bullet / ellipsis dot
}
APOSTROPHE = b"\x21\x47"                   # raw 2-byte JIS ’ (row 0x21 untouched)


def encode(text):
    """ASCII -> 1-byte English-build codes. Raises on unsupported characters.

    "..." becomes ・・・ (the game's own ellipsis convention); ' becomes the
    2-byte JIS ’ glyph (costs 2 bytes.. contractions are still usually
    byte-neutral vs. the spelled-out form)."""
    out = bytearray()
    text = text.replace("...", "\x01")            # placeholder, expanded below
    for ch in text:
        if ch == "\x01":
            out += b"\x19\x19\x19"
            continue
        if ch in ("'", "’"):
            out += APOSTROPHE
            continue
        o = ord(ch)
        if ch in _PUNCT:
            out.append(_PUNCT[ch])
        elif 0x30 <= o <= 0x39:                  # digit: native class
            out.append(0x50 + (o - 0x30))
        elif 0x41 <= o <= 0x5A or 0x61 <= o <= 0x73:   # A-Z, a-s
            out.append(0x5A + (o - 0x21))
        elif 0x74 <= o <= 0x7A:                  # t-z
            out.append(0xAD + (o - 0x74))
        else:
            raise ValueError(f"unsupported char {ch!r} for 1-byte English text")
    return bytes(out)


_REV = {0x04: " ", 0x16: ".", 0x15: ",", 0x1D: "!", 0x1C: "?", 0x1E: "-", 0x19: "・"}


def decode(data, control="⟨{:02x}⟩"):
    """Inverse of encode() (for offline verification of patched blocks)."""
    out = []
    i = 0
    while i < len(data):
        b = data[i]
        if data[i:i + 2] == APOSTROPHE:
            out.append("'")
            i += 2
            continue
        if b in _REV:
            out.append(_REV[b])
        elif 0x50 <= b <= 0x59:
            out.append(chr(0x30 + (b - 0x50)))
        elif 0x5A <= b <= 0xAC:
            out.append(chr(0x21 + (b - 0x5A)))
        elif 0xAD <= b <= 0xB3:
            out.append(chr(0x74 + (b - 0xAD)))
        elif b == 0x01:
            out.append("\n")
        else:
            out.append(control.format(b))
        i += 1
    return "".join(out)
