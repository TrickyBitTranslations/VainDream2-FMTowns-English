"""Rebuild dlz blocks from the translations in script/*.tsv.

export_script.py made script/<archive>.tsv: block_off / str_off / speaker / text.
Translators fill the 5th column `english`:
  - plain ASCII (glodia/english.py charset: A-Z a-z 0-9 . , ! ? - ' space)
  - \\n for line breaks, {NAME} or {hex} for ⟨02 nn⟩ name tokens ({REINA}, {2f})

Splices each translated string into its block (any length - the engine scans for
strings, so blocks resize freely), re-encodes, pads to the original member size,
and writes patched members + extracted/patches.json for patch_cd.py. Overflows
are reported and left original.

Usage: python tools/reinsert.py && python tools/patch_cd.py
"""
import base64, gzip, json, pathlib, re, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc, dlz, kana
from glodia.english import encode as en_encode
import patch_names

TRACK1_SECTORS = 2715
HALF = b"\x03\x03"
OUT_DIR = ROOT / "extracted" / "reinsert"
IMG = ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"
PACK = ROOT / "script" / "blockpack.json.gz"


def load_pack():
    return json.loads(gzip.decompress(PACK.read_bytes()))


class IsoSource:
    """Blocks straight from the game dump (required for building)."""

    def __init__(self):
        iso = disc.extract_track1_iso(str(IMG), TRACK1_SECTORS)
        self._iso = iso
        self._archives = {}

    def member(self, archive, off):
        if archive not in self._archives:
            self._archives[archive] = dict(
                dlz.iter_members(disc.read_file(self._iso, archive)))
        return self._archives[archive][off]

    def block(self, archive, off):
        return bytearray(dlz.decode(self.member(archive, off), prefix=bytes(0x40000)))

    def budget(self, archive, off):
        return len(self.member(archive, off))


class PackSource:
    """Blocks from script/blockpack.json.gz (validation without the dump)."""

    def __init__(self):
        self._pack = load_pack()

    def member(self, archive, off):
        return None                       # building needs the real dump

    def block(self, archive, off):
        e = self._pack["blocks"][archive][f"{off:#x}"]
        return bytearray(base64.b64decode(e["data"]))

    def budget(self, archive, off):
        return self._pack["blocks"][archive][f"{off:#x}"]["size"]


def load_speakers():
    """{kana_name: english} from script/SPEAKERS.tsv -- the literal-katakana
    NPC speaker labels embedded in the event stream (see export_speakers.py)."""
    path = ROOT / "script" / "SPEAKERS.tsv"
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            if len(c) >= 4 and c[3].strip():
                out[c[0]] = c[3].strip()
    return out


def speaker_label_splices(block, speakers):
    """[(start, end, english_bytes)] for every ``FF <kana> FF`` label in `block`
    whose kana is a known speaker name AND which is immediately followed by a
    dialogue-record opener (0x01/0x02/0x03). The opener check anchors the match
    to a real record so a stray FF<bytes>FF in event data is never rewritten.

    The CLOSING 0xFF is consumed along with the kana. The box title is rendered
    as the display string up to the first 0x01 (newline), so the structure
    ``FF <kana> FF <01> body`` puts the closing FF on the title line -- in the
    proper JIS font it's a katakana ン (the name's tail), but under our classifier
    patch 0xFF draws as 'F', giving "KayF". Replacing ``<kana> FF`` (kana + the
    trailing FF) with just the English leaves ``FF <english> <01> body`` -- the
    title is then exactly the English name, like a text-line speaker (e.g.
    "Rowney\\n..."). The opening FF stays as the event separator."""
    splices = []
    for name, english in speakers.items():
        raw = kana.encode(name)
        needle = b"\xff" + raw + b"\xff"
        i = block.find(needle)
        while i >= 0:
            after = i + len(needle)
            if after < len(block) and block[after] in (0x01, 0x02, 0x03):
                start = i + 1
                splices.append((start, start + len(raw) + 1, en_encode(english)))
            i = block.find(needle, i + 1)
    return splices


# Name-title bisections where the title isn't a SPEAKERS literal-kana name: a record
# ends with one of these and the next record is that NPC's line. Add a record's exact
# last line here once confirmed, and put a \p before that name in the TSV.
# Still open: ~11 sentence-flow FF junctions (a sentence split across two records, the
# FF drawing a stray 'F'); those need the FF stripped to merge, not a \p.
EXTRA_TITLES = {"{Knight} Ponar", "{Knight} Shaw", "Knight Show"}


def signoff_ff_splices(block, items, speakers):
    """When a record's text ENDS with a bare speaker name, that name is really the
    NEXT record's box title -- the game flows one record into the next with the
    name as the divider, and the export over-extends the text to the separator FF.
    That closing FF lands on the title line and (classifier patch) draws as 'F',
    so "Kay" shows as "KayF". Strip it. Anchored to translated records ending in a
    known speaker (or an EXTRA_TITLES name), so it never touches event-data byte
    coincidences. (Pair with a `\\p` before the trailing name in the TSV so it
    titles a fresh page.)"""
    names = set(speakers.values()) | EXTRA_TITLES
    out = []
    for str_off, english in items:
        last = english.replace("\\p", "\\n").split("\\n")[-1].strip()
        if last in names:
            _start, end = string_span(block, str_off)
            if end < len(block) and block[end] == 0xFF:
                out.append((end, end + 1, b""))
    return out


def unhandled_ff_junctions(block, items, speakers):
    """Translated records that flow into the next box via a separator FF (span end
    == 0xFF) but are NOT handled by signoff_ff_splices -- each still draws a stray
    'F' at the junction (the ~11 sentence-flow bisections; see EXTRA_TITLES and
    docs/findings). Returns [(str_off, last_line)] for a standing build reminder."""
    names = set(speakers.values()) | EXTRA_TITLES
    out = []
    for str_off, english in items:
        last = english.replace("\\p", "\\n").split("\\n")[-1].strip()
        if last in names:
            continue
        _start, end = string_span(block, str_off)
        if end < len(block) and block[end] == 0xFF:
            out.append((str_off, last))
    return out


def name_token_map():
    """EN name -> token byte: from NAME.P if the dump is around, else the pack."""
    data_bin = ROOT / "floppy_files" / "DATA.BIN"
    if data_bin.exists():
        from glodia.script import load_names
        names = load_names(data_bin.read_bytes())
        return {patch_names.TRANSLATIONS[jp].upper(): tok
                for tok, jp in names.items() if jp in patch_names.TRANSLATIONS}
    return {k: v for k, v in load_pack()["tokens"].items()}


TYPEWRITER = b"\x03\x30"    # per-char delay 8 ([0x2df]) - the typewriter effect.
                            # Originals set this right after the box title; we
                            # replace that span, so re-emit it per string.


def _closest_token(key, tokens):
    """Nearest known name token to a misspelled {KEY}, or None."""
    import difflib
    m = difflib.get_close_matches(key.upper(), tokens.keys(), n=1, cutoff=0.6)
    return m[0].title() if m else None


def compile_english(text, tokens):
    """Translate the TSV `english` syntax to engine bytes. (Half-width is the
    engine DEFAULT now - patch_main_exp.py, so no ⟨03 03⟩ prefix needed.)"""
    out = bytearray(TYPEWRITER)
    for part in re.split(r"(\{[^}]+\}|\\n|\\p)", text):
        if not part:
            continue
        if part == "\\n":
            out += b"\x01"
        elif part == "\\p":
            out += b"\x03\x50"          # wait-for-key + clear box (next page)
        elif part.startswith("{"):
            key = part[1:-1]
            tok = tokens.get(key.upper())
            if tok is None:
                # allow a raw hex token id; otherwise it's an unknown name
                try:
                    tok = int(key, 16)
                except ValueError:
                    hint = _closest_token(key, tokens)
                    raise ValueError(
                        f"unknown name token {{{key}}}"
                        + (f" - did you mean {{{hint}}}?" if hint else "")
                        + " (see tools/reinsert.py --tokens for the list)")
            out += bytes([0x02, tok])
        else:
            out += en_encode(part)
    return bytes(out)


def string_span(block, str_off):
    """(prefix_end, end): preserve leading fmt ops + the ⟨02 spk⟩⟨01⟩ box-title
    prefix; the replaceable text runs to the string's 0x00 terminator.

    0xff is *usually* an event separator - but 0xff is also the katakana ン, and
    the two are byte-identical. It's a real ン only when wedged inside a katakana
    run (both neighbours are katakana, 0xad-0xff), e.g. ジャイア|ン|ト; there we
    read through it. Anywhere else the 0xff ends the string, so a splice never
    crosses event bytecode. (Mirrors glodia.script.parse_string.)"""
    j = str_off
    while block[j] == 0x03:
        j += 2
    if block[j] == 0x02 and j + 2 < len(block) and block[j + 2] == 0x01:
        j += 3
    elif block[j] == 0x01:
        j += 1
    end = j
    while end < len(block) and block[end] != 0x00:
        if block[end] == 0xFF:
            prev = block[end - 1] if end else 0
            nxt = block[end + 1] if end + 1 < len(block) else 0
            if not (0xAD <= prev <= 0xFF and 0xAD <= nxt <= 0xFF):
                break                  # event separator, not katakana ン
        end += 1
    return j, end


def spans_event_code(block, start, end):
    """True if [start,end) crosses event bytecode and must not be spliced.

    Walk the bytes as the text grammar (⟨02 nn⟩ name, ⟨03 nn⟩ fmt, and 2-byte
    kanji leads each consume an operand); a *bare* event opcode (0x05-0x13) means
    str_off was mis-extracted into event code. A lone 0xff (katakana ン) is fine."""
    i = start
    while i < end:
        b = block[i]
        if b in (0x02, 0x03) or 0x21 <= b <= 0x4F:   # 2-byte: name / fmt / kanji
            i += 2
        elif 0x05 <= b <= 0x13:
            return True
        else:
            i += 1
    return False


MAX_LINE = 37           # half-width cells per line. The field box is ~37 wide
                        # (wraps mid-word at cell 38); break with \n, page with \p.


def visual_lines(text, names):
    """Rendered line lengths in half-width cells ({NAME} expands, ' = 1 cell)."""
    expanded = re.sub(r"\{([^}]+)\}",
                      lambda m: names.get(m.group(1).upper(), "??"), text)
    expanded = expanded.replace("'", "x").replace("...", "xxx")
    return [len(l) for chunk in expanded.split("\\p") for l in chunk.split("\\n")]


def load_rows():
    """[(archive, block_off, str_off, english, tsv_name, line_no)] from script/."""
    rows = []
    for tsv in sorted((ROOT / "script").glob("*.tsv")):
        # Only the dialogue TSVs (VAIN_*_DAT, *_PK) are dlz CD blocks. Others
        # (NAMES.tsv -> patch_names, *_TOS.tsv -> patch_ui) have a non-hex
        # block_off and their own reinserters.
        if not (tsv.stem.endswith("_DAT") or tsv.stem.endswith("_PK")):
            continue
        archive = tsv.stem.replace("_DAT", ".DAT").replace("_PK", ".PK")
        for ln, row in enumerate(tsv.read_text(encoding="utf-8").splitlines()[1:],
                                 start=2):
            cols = row.split("\t")
            if len(cols) >= 5 and cols[4].strip():
                rows.append((archive, int(cols[0], 16), int(cols[1], 16),
                             cols[4].strip(), tsv.name, ln))
    return rows


def main():
    check = "--check" in sys.argv
    tokens = name_token_map()
    speakers = load_speakers()
    rev_names = {patch_names.TRANSLATIONS[jp].upper(): patch_names.TRANSLATIONS[jp]
                 for jp in patch_names.TRANSLATIONS}

    if "--tokens" in sys.argv:
        print("{NAME} tokens usable in translations (case-insensitive):")
        for en, tok in sorted(tokens.items()):
            print(f"  {{{en}}}  = token {tok:#04x}")
        return

    rows = load_rows()
    errors = warnings = 0
    per_block = defaultdict(list)
    for archive, block_off, str_off, english, tsv_name, ln in rows:
        where = f"{tsv_name}:{ln}"
        try:
            compile_english(english, tokens)
        except (ValueError, KeyError) as e:
            print(f"ERROR  {where}: {e}")
            errors += 1
            continue
        for i, width in enumerate(visual_lines(english, rev_names), 1):
            if width > MAX_LINE:
                print(f"WARN   {where}: rendered line {i} is {width} cells "
                      f"(max ~{MAX_LINE}) - will be cut off or wrapped mid-word")
                warnings += 1
        per_block[(archive, block_off)].append((str_off, english))

    # size guard: a git-LFS checkout without LFS leaves a tiny pointer file
    if IMG.exists() and IMG.stat().st_size > 1_000_000:
        src = IsoSource()
    elif check and PACK.exists():
        src = PackSource()
        print("(game dump absent - validating against script/blockpack.json.gz)")
    elif check:
        sys.exit("need either the game dump or script/blockpack.json.gz")
    else:
        sys.exit("building requires the game dump (validation: use --check)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    total = fitted = 0
    bisection_todo = []              # FF-junctions still drawing a stray 'F' (reminder)
    for (archive, block_off), items in sorted(per_block.items()):
        block = src.block(archive, block_off)
        budget = src.budget(archive, block_off)
        total += len(items)
        # collect every splice (translated records + literal-kana speaker labels)
        # with ORIGINAL offsets, then apply high->low so earlier offsets stay valid.
        splices = []
        for str_off, english in items:
            start, end = string_span(block, str_off)
            if spans_event_code(block, start, end):   # mis-extracted into event code
                print(f"ERROR  {archive}@{block_off:#x} str {str_off:#x}: original "
                      f"spans event bytecode (0x05-0x13) - not a real string, don't translate")
                errors += 1
                continue
            splices.append((start, end, compile_english(english, tokens)))
        labels = speaker_label_splices(block, speakers)
        splices.extend(labels)
        splices.extend(signoff_ff_splices(block, items, speakers))
        bisection_todo += unhandled_ff_junctions(block, items, speakers)
        for start, end, repl in sorted(splices, key=lambda s: s[0], reverse=True):
            block[start:end] = repl
        encoded = dlz.encode(bytes(block))
        # No size cap: grow_build.py grows archives and repoints the scene table,
        # so any length fits. Size below is just for reference vs the old slot.
        print(f"  {archive}@{block_off:#x}: {len(items)} strings"
              + (f" +{len(labels)} speaker label(s)" if labels else "")
              + f", {len(encoded)} bytes (was {budget})")
        fitted += len(items)
        if check:
            continue
        member = src.member(archive, block_off)
        new_member = bytearray(dlz.encode(bytes(block), pad_to=len(member)))
        new_member[8:13] = member[8:13]
        assert dlz.decode(bytes(new_member)) == bytes(block)
        binp = OUT_DIR / f"{archive.replace('.', '_')}_{block_off:#x}.bin"
        binp.write_bytes(bytes(new_member))
        manifest.append({"file": archive, "offset": block_off,
                         "bin": str(binp.relative_to(ROOT))})

    if not check:
        (ROOT / "extracted" / "patches.json").write_text(json.dumps(manifest, indent=1))
    verb = "validated" if check else "inserted"
    print(f"\n{fitted}/{total} translated strings {verb}; "
          f"{errors} error(s), {warnings} warning(s)")
    if bisection_todo:
        print(f"NOTE: {len(bisection_todo)} dialogue FF-junction(s) still draw a stray 'F' "
              f"(unhandled bisections to merge) - see memory dialogue-ff-bisection-todo")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
