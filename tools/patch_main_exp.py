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
