"""Rebuild a dlz archive allowing members to change size, and recompute the
member-offset table the engine uses to seek to each scene.

The game finds member N in an archive via a u32 offset table in MAIN.EXP
(VAIN_A @0x29ed8, VAIN_S @0x29b68, VAIN_A @..., see TABLES). Members are
self-describing (each header carries its comp_size), so we can grow any member
and just (a) re-concatenate, (b) rewrite the offset table, (c) grow the archive
file on the disc. This removes the per-scene compressed-size budget.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import dlz

# MAIN.EXP file offset of each archive's u32 member-offset table (count = members)
TABLES = {
    "VAIN_S.DAT": 0x29B68,
    "VAIN_A.DAT": 0x29ED8,
    "VAIN_B.DAT": 0x2A110,
    "VAIN_C.DAT": 0x2A34C,
}


def rebuild(archive_bytes, overrides):
    """Re-concatenate `archive_bytes`' members, replacing any whose original
    start offset is in `overrides` (offset -> new full member bytes).

    Returns (new_archive_bytes, [new member start offsets]). Each new member
    keeps the dlz chain valid (its header's comp_size matches its body), so the
    engine's size-walk still works and the new offsets index it correctly.
    """
    out = bytearray()
    offsets = []
    for off, member in dlz.iter_members(archive_bytes):
        offsets.append(len(out))
        out += overrides.get(off, member)
    return bytes(out), offsets


def patch_offset_table(exe, archive, old_offsets, new_offsets, old_size, new_size):
    """Repoint `archive`'s scene table in MAIN.EXP (in place, length-preserving).

    The table is `[u32 offset]* [u32 archive-size terminator]`. Entries are byte
    offsets INTO the archive -- mostly member starts, but some are *sub-offsets*
    that point inside a member (a scene that begins partway through a block).
    EVERY entry must shift by however many bytes the (translated) members before
    it grew or shrank, not just the ones that equal a member start. So remap each
    entry by the byte-delta of the member that CONTAINS it; the terminator
    becomes the new archive size.

    (The previous version remapped only exact member-start values and bailed at
    the first sub-offset it didn't recognise -- leaving the rest of the table AND
    the size terminator stale. For an archive that resized, that pointed every
    scene indexed past the first sub-offset at the wrong place: e.g. VAIN_S left
    64 stale entries, so a scene load computed a garbage sector and the CD BIOS
    trapped. Member starts still map exactly, sub-offsets map start+delta.)
    """
    import struct, bisect
    base = TABLES[archive]
    # hard upper bound: the next table (tables are clustered) or EOF, so a walk
    # never bleeds into an adjacent archive's table
    higher = [t for t in TABLES.values() if t > base]
    end = min(higher) if higher else len(exe)
    pairs = sorted(zip(old_offsets, new_offsets))        # (old_start, new_start)
    olds = [o for o, _ in pairs]

    def remap(v):
        if v == old_size:
            return new_size                              # archive-size terminator
        j = bisect.bisect_right(olds, v) - 1             # member containing v
        if j < 0:
            return v
        o, n = pairs[j]
        return n + (v - o)                               # start + in-member delta

    exe = bytearray(exe)
    i = changed = 0
    while base + (i + 1) * 4 <= end:
        pos = base + i * 4
        v = struct.unpack("<I", exe[pos:pos + 4])[0]
        nv = remap(v)
        if nv != v:
            exe[pos:pos + 4] = struct.pack("<I", nv)
            changed += 1
        i += 1
        if v == old_size:                                # terminator ends the table
            break
    return bytes(exe), i, changed
