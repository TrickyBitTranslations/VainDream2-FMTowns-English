"""Batch reinserter: rebuild dlz blocks from translations in script/*.tsv.

Workflow:
  1. tools/export_script.py produced script/<archive>.tsv with columns
     block_off / str_off / speaker / text.
  2. Translators add a 5th column `english` to rows they translate:
       - plain ASCII (glodia/english.py charset: A-Z a-z 0-9 . , ! ? - ' space)
       - \\n for line breaks, {NAME} or {hex} for ⟨02 nn⟩ name tokens
         (e.g. {REINA}, {WARRICK}, {2f})
  3. This tool splices every translated string into its block (any length -
     the engine scans for strings, so blocks resize freely), re-encodes with the optimal-parse
     dlz encoder, pads to the exact original member size, and emits patched
     member binaries + extracted/patches.json for tools/patch_cd.py.

Strings whose block no longer fits its compressed envelope are reported with
the overflow so the translator can shorten them; the block is left original.

Usage: python tools/reinsert.py && python tools/patch_cd.py
"""
import base64, gzip, json, pathlib, re, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc, dlz
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
                tok = int(key, 16)
            out += bytes([0x02, tok])
        else:
            out += en_encode(part)
    return bytes(out)


def string_span(block, str_off):
    """(prefix_end, end_excl_terminator): preserve leading fmt ops + the
    ⟨02 spk⟩⟨01⟩ box-title prefix; the replaceable text runs to the 0x00."""
    j = str_off
    while block[j] == 0x03:
        j += 2
    if block[j] == 0x02 and j + 2 < len(block) and block[j + 2] == 0x01:
        j += 3
    elif block[j] == 0x01:
        j += 1
    end = block.index(b"\x00", j)
    return j, end


MAX_LINE = 54           # visual half-width cells per dialogue-box line


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
    for (archive, block_off), items in sorted(per_block.items()):
        block = src.block(archive, block_off)
        budget = src.budget(archive, block_off)
        total += len(items)
        for str_off, english in sorted(items, reverse=True):   # splice high->low
            start, end = string_span(block, str_off)
            block[start:end] = compile_english(english, tokens)
        encoded = dlz.encode(bytes(block))
        free = budget - len(encoded)
        if free < 0:
            print(f"OVERFLOW {archive}@{block_off:#x}: {-free} bytes over budget "
                  f"({len(items)} strings) - shorten translations in this block")
            errors += 1
            continue
        print(f"  {archive}@{block_off:#x}: {len(items)} strings, "
              f"{len(encoded)}/{budget} bytes ({free} free)")
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
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
