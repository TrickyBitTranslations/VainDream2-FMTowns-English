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

    The table is `[u32 member-offset]* [u32 archive-size terminator]`; entries
    may repeat (scenes sharing a block). We remap by VALUE: every entry equal to
    an old member offset becomes its new offset; the size terminator becomes the
    new size. Walks consecutive valid entries from the table base so we touch
    exactly the table and nothing after it. Returns new bytes + entries changed.
    """
    import struct
    base = TABLES[archive]
    # hard upper bound: the next table (tables are clustered) or EOF, so a walk
    # never bleeds into an adjacent archive's table
    higher = [t for t in TABLES.values() if t > base]
    end = min(higher) if higher else len(exe)
    remap = dict(zip(old_offsets, new_offsets))
    remap[old_size] = new_size
    valid = set(old_offsets) | {old_size}
    exe = bytearray(exe)
    i = changed = 0
    while base + (i + 1) * 4 <= end:
        pos = base + i * 4
        v = struct.unpack("<I", exe[pos:pos + 4])[0]
        if v not in valid:
            break                       # past the table
        nv = remap[v]
        if nv != v:
            exe[pos:pos + 4] = struct.pack("<I", nv)
            changed += 1
        i += 1
    return bytes(exe), i, changed
