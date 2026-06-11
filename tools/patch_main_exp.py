"""Patch MAIN.EXP's text classifier for 1-byte ASCII (the English build).

Bytes changed in the renderer (kana classifier @0x4877 + entry points):

    0x4892  mov bx, 0x2421   ->  mov bx, 0x2321   (hiragana range -> JIS row 0x23)
    0x489f  mov bx, 0x2521   ->  mov bx, 0x2374   (katakana range -> row 0x23 @ 't')

After this, bytes 0x5a..0xac render ASCII 0x21..0x73 and 0xad+ continue t..z.
Japanese kana text NO LONGER RENDERS - this floppy is for the English build only.
We might need to revist this strategy?

Emits "...[SystemDisk]_EN.D88" (original untouched). Boot it together with the
patched "... [EN].img" CD.

Usage: python tools/patch_main_exp.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88

SRC = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88"
OUT = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"

PATCHES = [  # (offset in MAIN.EXP, expected original, replacement)
    (0x4895, b"\x24", b"\x23"),          # imm hi of mov bx,0x2421
    (0x48A1, b"\x21\x25", b"\x74\x23"),  # imm of mov bx,0x2521
    # half-width by DEFAULT: renderer entries do `mov bh,2` -> [0x2d3];
    # 1 = half-cell advance + condensed glyphs. Saves the per-string <03 03>
    # toggle (2 bytes/string of compressed budget).
    (0x448E, b"\x02", b"\x01"),
    (0x44A3, b"\x02", b"\x01"),

    # --- Name-table relocation, step 1: route the character-name lookup through a
    # 32-bit copy of the table-lookup routine, so the name base is no longer
    # truncated to 16 bits (the original `0x42b6` does `movzx ebx,bx`). This step
    # keeps the base at the CURRENT table (0x301B) to prove the new path renders
    # names identically before the table actually moves (step 2). See
    # docs/findings/2026-06-11-phase-o (private repo).
    #
    # 32-bit lookup variant in the runtime-free EXE hole @0x982 = a verbatim copy
    # of 0x42b6 with `movzx ebx,bx` (0f b7 db) replaced by 3 NOPs:
    (0x982, b"\x00" * 64, bytes.fromhex(
        "51068e05f6010000" "32d2" "83c308" "909090" "3c02" "0f82210000" "00"
        "fec8" "8ae0" "32c0" "33c9" "49" "87fb" "f2ae" "6626837ffe00"
        "0f85020000" "00" "fec2" "fecc" "75ec" "87fb" "8ac2" "8bd3" "07" "59" "c3")),
    # char-name handler @0x46a2: `mov bx,gs:[0x2018]` -> `mov ebx,0x301B` + 3 NOPs
    (0x46A2, bytes.fromhex("6665" "8b1d" "18200000"),
             bytes.fromhex("bb1b300000" "909090")),
    # @0x46aa: `call 0x42b6` -> `call 0x982` (the 32-bit variant)
    (0x46AA, bytes.fromhex("e807fcffff"), bytes.fromhex("e8d3c2ffff")),

    # --- Scene-buffer enlargement, step 1 (boot-only POC): carve a dedicated RAM
    # segment. The main data segment and the two aux data segments are full to
    # their limits, and init grabs ALL remaining RAM for the heap, so there is no
    # free home for a bigger scene buffer. Carve one: init sizes the heap with a
    # query-then-grab -- 0x230f queries free RAM into ebx (alloc of 0xffffffff
    # paras fails and returns the largest block), 0x2318 then allocates ebx paras
    # as the heap (selector stored at [0x1fe]). Trampoline the grab so it first
    # subtracts 0x200 paragraphs (8 KB), allocates the smaller heap (selector
    # unchanged), then allocates the freed 8 KB as a fresh segment whose selector
    # is saved at the EXE hole word 0x9c2. The carved segment is allocated LAST so
    # no existing selector number shifts. Nothing uses it yet -- this build only
    # proves the carve boots; step 2 moves the scene buffer into it.
    #
    # trampoline @0x2318: (mov ah,48; int21; mov [0x1fe],ax; ret) -> jmp 0x9c4 + nops
    (0x2318, bytes.fromhex("b448" "cd21" "66a3fe010000" "c3"),
             bytes.fromhex("e9a7e6ffff" "909090909090")),
    # 0x9c2..0x9c3: carved-segment selector storage (stays 0; written at runtime).
    # carve stub @0x9c4 (the runtime-free EXE hole, after the 64-byte name variant):
    (0x9C4, b"\x00" * 32, bytes.fromhex(
        "81eb00020000"   # sub ebx, 0x200          ; leave 8 KB for the carved seg
        "b448" "cd21"    # mov ah,0x48 / int 0x21   ; alloc heap (avail-8KB) -> ax
        "66a3fe010000"   # mov [0x1fe], ax          ; heap selector (unchanged slot)
        "b448"           # mov ah,0x48
        "bb00020000"     # mov ebx, 0x200           ; 8 KB
        "cd21"           # int 0x21                 ; alloc carved seg -> ax
        "66a3c2090000"   # mov [0x9c2], ax          ; carved-segment selector
        "c3")),          # ret
]


def main():
    image = SRC.read_bytes()
    for off, orig, repl in PATCHES:
        d88 = read_d88(image)
        flat = d88.flat_offset_for_file("MAIN.EXP", off)
        cur = d88.flat[flat:flat + len(orig)]
        if cur == repl:
            print(f"MAIN.EXP+{off:#x}: already patched")
            continue
        assert cur == orig, f"MAIN.EXP+{off:#x}: expected {orig.hex()} found {cur.hex()}"
        image = d88.patch(flat, repl)
        print(f"MAIN.EXP+{off:#x}: {orig.hex()} -> {repl.hex()}")
    assert len(image) == SRC.stat().st_size
    OUT.write_bytes(image)
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
