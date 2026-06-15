#!/usr/bin/env python3
"""Lays out each script line the way the game would and flags ones that won't fit.
No emulator needed.

  WIDE     line wider than the box (wraps mid-word)
  TALL     box has more lines than it shows
  REDTITLE page break not followed by a name, so the body draws red

Box size below is a starting guess. Tune it against real captures.
Pairs with reinsert.py --check (charset/tokens + FF-junction bisections).
"""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import reinsert, patch_names

# box size - field box. portrait/system boxes differ, tune against captures.
BOX_WIDTH = 37
BOX_LINES = 6

NAMES = {patch_names.TRANSLATIONS[j].upper(): patch_names.TRANSLATIONS[j]
         for j in patch_names.TRANSLATIONS}


def to_cells(line):
    """line -> rendered cells, for measuring width."""
    line = re.sub(r"\{([^}]+)\}", lambda m: NAMES.get(m.group(1).upper(), "??"), line)
    line = line.replace("３", "").replace("７", "")     # highlight markers: drop
    line = line.replace("...", "\x00\x00\x00").replace("…", "\x00")
    line = line.replace("'", "x").replace("・", "x")
    return line.replace("\x00", "x")


def hard_wrap(cells, width):
    if len(cells) <= width:
        return [cells]
    return [cells[i:i + width] for i in range(0, len(cells), width)]


def layout(english):
    """[(box_index, [rendered_lines], [src_line_widths])] for an english string."""
    out = []
    for bi, box in enumerate(english.split("\\p")):
        rendered, src_widths = [], []
        for src in box.split("\\n"):
            cells = to_cells(src)
            src_widths.append(len(cells))
            rendered.extend(hard_wrap(cells, BOX_WIDTH))
        out.append((bi, rendered, src_widths))
    return out


def looks_like_name(line):
    """is this the speaker name (the red title line after a page break)?"""
    s = line.strip()
    if not s:
        return False
    if s in NAMES.values():
        return True
    words = s.split()
    return len(words) <= 2 and s[:1].isupper() and not s.endswith((".", "!", "?", ","))


def check(english):
    flags = []
    boxes = layout(english)
    for bi, rendered, src_widths in boxes:
        for i, w in enumerate(src_widths, 1):
            if w > BOX_WIDTH:
                flags.append(("WIDE", f"box {bi} line {i}: {w} cells > {BOX_WIDTH} "
                                      f"(wraps mid-word)"))
        if len(rendered) > BOX_LINES:
            flags.append(("TALL", f"box {bi}: {len(rendered)} rendered lines "
                                  f"> {BOX_LINES}"))
        if bi > 0 and rendered and not looks_like_name(rendered[0]):
            flags.append(("REDTITLE", f"box {bi} after \\p starts with "
                                      f"'{rendered[0][:24]}' (not a name -> renders red)"))
    return flags


def main():
    rows = reinsert.load_rows()
    counts = {"WIDE": 0, "TALL": 0, "REDTITLE": 0}
    n_records = n_flagged = 0
    show = "--list" in sys.argv
    for archive, block_off, str_off, english, tsv_name, ln in rows:
        n_records += 1
        flags = check(english)
        if flags:
            n_flagged += 1
            for kind, msg in flags:
                counts[kind] += 1
                if show:
                    print(f"{kind:9} {tsv_name}:{ln} ({block_off:#x}/{str_off:#x})  {msg}")
    print(f"\n=== fitment: {n_records} records, {n_flagged} with issues "
          f"(BOX {BOX_WIDTH}x{BOX_LINES}, PROVISIONAL) ===")
    for k, v in counts.items():
        print(f"  {k:9} {v}")
    print("  (run with --list to see each; calibrate BOX_WIDTH/BOX_LINES vs 0x2E51 captures)")


if __name__ == "__main__":
    main()
