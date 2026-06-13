#!/usr/bin/env python3
"""Static dialogue fitment / flow checker.

Simulates the engine's text-box layout over the translated script (no emulator,
no playthrough) and flags lines/boxes that won't render correctly. This is the
fast, exhaustive per-build gate; the emulator (BP 0x2E51 dialogue-box catch) is
the calibration oracle for the geometry constants below.

Models:
  - glyph cell widths: half-width codec; {TOKEN} -> rendered name, ' = 1, ... = 3,
    middot = 1; 3<word>7 highlight markers dropped.
  - engine hard-wrap: a line longer than the box wraps mid-word at the box edge
    (live-measured: overworld box wraps at cell 38).
  - \\n = line break, \\p = new box; a box shows up to BOX_LINES lines; the FIRST
    line after a \\p renders in title (red) colour, so it must be a speaker name.

Flags per record:
  WIDE     a source line is wider than the box -> hard-wraps mid-word (ugly).
  TALL     a box (after wrapping) has more lines than the box can show.
  REDTITLE a \\p is not followed by a name line -> body text renders red.

Complements `reinsert.py --check` (charset/token validity + FF-junction
bisections). Geometry constants are PROVISIONAL until calibrated against
in-engine captures -- see docs/plans/dialogue-test-harness.md.
"""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import reinsert, patch_names

# --- box geometry (CALIBRATE against 0x2E51 captures) ------------------------
# Defaults = overworld field-NPC box. Portrait/system boxes differ (TBD).
BOX_WIDTH = 37          # half-width cells per line
BOX_LINES = 6           # lines a box shows before it scrolls/overflows

NAMES = {patch_names.TRANSLATIONS[j].upper(): patch_names.TRANSLATIONS[j]
         for j in patch_names.TRANSLATIONS}


def to_cells(line):
    """A source line -> its rendered half-width cell string (for width/wrap)."""
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
    """First-line-after-\\p title test: a known name, or a short Title-Cased word."""
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
