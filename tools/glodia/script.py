"""Parse dialogue strings out of decompressed Glodia scene blocks.

Grammar (reverse-engineered from the MAIN.EXP text renderer @0x44cd/0x45f4):

  0x00        end of string
  0x01        newline
  0x02 nn     insert name/term #nn (1-based record in the NAME.P table)
  0x03 nn     formatting op, one arg (pause/color/speed/voice/wait-key...)
  0x04        cursor right one cell
  0x05-0x13   NEVER valid inside text (event-interpreter opcodes) -> run aborts
  0x14-0x20   single punctuation glyph (firmware table; mapped empirically)
  0x21-0x4f   kanji lead byte -> 2-byte raw JIS X 0208
  0x50-0xff   digit / hiragana / katakana (see glodia.kana)
"""
from glodia.kana import decode as kana_decode

PUNCT = {
    0x14: "⟨14⟩", 0x15: "、", 0x16: "。", 0x17: "⟨17⟩", 0x18: "⟨18⟩",
    0x19: "・", 0x1A: "⟨1a⟩", 0x1B: "⟨1b⟩", 0x1C: "？", 0x1D: "！",
    0x1E: "ー", 0x1F: "⟨1f⟩", 0x20: "◇",   # 0x20 draws ◇ in dialogue
}                                          
WAIT_KEY = 0x50         # ⟨03 50⟩ = wait for key + clear box


def _decode_record(raw):
    """Decode a name-table record: text plus the punctuation/space controls."""
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if b == 0x04:
            out.append("　"); i += 1
        elif 0x14 <= b <= 0x20:
            out.append(PUNCT[b]); i += 1
        elif b < 0x14:
            i += 1                       # stray control, drop
        elif b <= 0x4F:
            out.append(kana_decode(raw[i:i + 2], unknown="")); i += 2
        else:
            out.append(kana_decode(raw[i:i + 1], unknown="")); i += 1
    return "".join(out)


def load_names(data_bin, table_off=4123):
    """Name/term table from DATA.BIN: 8-byte header, then NUL-terminated records,
    tokens are 1-based, EMPTY records count (engine lookup @0x42b6)."""
    recs = data_bin[table_off + 8:].split(b"\x00")
    names = {}
    for i, r in enumerate(recs[:0x100]):
        if r:
            names[i + 1] = _decode_record(r)
    return names


def parse_string(data, i, names):
    """Try to parse a dialogue string at offset i.

    Returns (end_offset, text, speaker, n_glyphs) or None if the bytes don't
    form valid text. `speaker` is the name-token if the string opens with
    ⟨02 nn⟩ before any glyph (the box-title convention)."""
    out = []
    speaker = None
    glyphs = 0
    seen_glyph = False
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x00:
            return i + 1, "".join(out), speaker, glyphs
        if b == 0x01:
            out.append("\n"); i += 1
        elif b == 0x02:
            if i + 1 >= n:
                return None
            tok = data[i + 1]
            name = names.get(tok)
            if name is None:
                return None
            # box-title convention: ⟨02 nn⟩⟨01⟩ before any glyph = speaker
            if (not seen_glyph and speaker is None
                    and i + 2 < n and data[i + 2] == 0x01):
                speaker = name
                i += 3                  # swallow the title newline too
            else:
                out.append(name)
                glyphs += len(name)
                seen_glyph = True
                i += 2
        elif b == 0x03:
            if i + 1 >= n:
                return None
            if data[i + 1] == WAIT_KEY:
                out.append("\n")        # page break
            i += 2
        elif b == 0x04:
            out.append("　"); i += 1
        elif b < 0x14:
            return None                 # event opcode -> not text
        elif b <= 0x20:
            out.append(PUNCT[b]); i += 1
            if b != 0x20:
                glyphs += 1
                seen_glyph = True
        elif b <= 0x4F:                 # kanji pair
            if i + 1 >= n or not (0x21 <= data[i + 1] <= 0x7E):
                return None
            ch = kana_decode(data[i:i + 2], unknown="�")
            if "�" in ch:
                return None
            out.append(ch)
            glyphs += 1
            seen_glyph = True
            i += 2
        else:                           # digit / kana
            out.append(kana_decode(data[i:i + 1]))
            glyphs += 1
            seen_glyph = True
            i += 1
    return None                         # ran off the end


# word pairs you'd see in actual dialogue, for scoring lines with no punctuation
COMMON = ["のだ", "です", "ます", "ている", "から", "こと", "して", "ない", "った",
          "いる", "する", "ません", "ください", "けど", "だろ", "ので", "のよ",
          "わよ", "かな", "んだ", "のか", "まで", "ても", "たら", "という", "には"]


def _accept(text, speaker, glyphs, min_glyphs):
    """Reject pixel-noise that happens to parse (e.g. ゑょょょ, ンンンン)."""
    if glyphs < min_glyphs or not text:
        return False
    if text[0] in "ンー⟨◇":              # no Japanese line starts with these
        return False
    if text.count("⟨") > 2:              # too many unknown glyphs = bytecode
        return False
    hira = sum(1 for c in text if "ぁ" <= c <= "ん")
    if hira < 2:
        return False
    if len(set(text)) / len(text) < 0.3:
        return False
    if any(p in text for p in "、。？！"):
        return True
    if any(b in text for b in COMMON):
        return True
    return speaker is not None


def extract_strings(block, names, min_glyphs=4):
    """Scan a decompressed block for dialogue strings.

    Yields (offset, speaker, text). Greedy: tries every offset, accepts coherent
    runs ending in 0x00, then skips past them. Blocks whose output starts with
    "PICT" are images, skip those before calling this.
    """
    i = 0
    n = len(block)
    while i < n:
        b = block[i]
        # plausible string openers: speaker token, newline-start, fmt, or a glyph
        # (never 0xff, that's the event-stream separator, ン only mid-text)
        if b != 0xFF and (b in (0x01, 0x02, 0x03) or 0x15 <= b):
            r = parse_string(block, i, names)
            if r:
                end, text, speaker, glyphs = r
                text = text.strip("\n　 ")
                if _accept(text, speaker, glyphs, min_glyphs):
                    yield i, speaker, text
                    i = end
                    continue
        i += 1
