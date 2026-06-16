"""Patch MAIN.EXP's text classifier so 1-byte ASCII renders (English build).

Renderer kana classifier @0x4877:
    0x4892  mov bx,0x2421 -> 0x2321   (hiragana range -> JIS row 0x23)
    0x489f  mov bx,0x2521 -> 0x2374   (katakana range -> row 0x23 @ 't')
After this, 0x5a..0xac render ASCII 0x21..0x73 and 0xad+ continue t..z. JP kana
no longer renders - English build only.

Writes "...[SystemDisk]_EN.D88" (original untouched). Boot with the [EN].img CD.
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
    # half-width default: renderer entries set bh=2 -> [0x2d3]; 1 = half advance.
    (0x448E, b"\x02", b"\x01"),
    (0x44A3, b"\x02", b"\x01"),
    # <03 03> is a per-string width toggle (handler @0x4622 flips [0x2d3] 1<->2).
    # Forcing half-default above inverted it: records still carrying <03 03>
    # (currency, "Level", hit-counts) flipped to full and overflowed - "Dain"->
    # "Dai"+orphan "n", and that "n" wrecked the shop icon column. Pin to always-half
    # by making the half->full branch also write 1 (@0x4635), so prices/icons fit.
    (0x4835, b"\x02", b"\x01"),
    # Character-name render entry @0x381f sets bh=2 (full) then jumps into the
    # shared renderer, so party/status names drew full-width and "Warrick" spilled
    # past the panel box. Half-width here makes names fit, like dialogue.
    (0x3A20, b"\x02", b"\x01"),

    # Name-table relocation: the full NAME.P table rides in ITEM.TOS and loads into
    # the carved segment at carved:0x2000 (see patch_items), off DATA.BIN's cap.
    # Repoint the char-name handler @0x46aa at a lookup variant: scan carved
    # (ES=[0x9c2]) for the Nth NUL-record, copy it to a low DATA_SEG scratch (0x3f40),
    # return that offset. (Naive high-address moves failed - the renderer's
    # `movzx edx,dx` truncates the offset, so the record has to live low.)
    # variant @0xa80 = the item variant @0xa03 with scratch 0x3ef2 -> 0x3f40:
    (0xA80, b"\x00" * 94, bytes.fromhex(
        "51565766" "068e05c2090000" "30d2" "83c308" "0fb7db" "3c02" "721d" "fec8" "88c4"
        "30c0" "31c9" "49" "87fb" "f2ae" "2666837ffe00" "7502" "fec2" "fecc" "75f0" "87fb"
        "89de" "bf403f0000" "b940000000" "268a06" "658807" "46" "47" "20c0" "7407" "49"
        "75f1" "65c60700" "ba403f0000" "6607" "5f" "5e" "59" "c3")),
    # char-name handler @0x46a2: `mov bx,gs:[0x2018]` -> `mov ebx,0x2000` (carved NAME.P
    # base) + 3 NOPs:
    (0x46A2, bytes.fromhex("6665" "8b1d" "18200000"),
             bytes.fromhex("bb00200000" "909090")),
    # @0x46aa: `call 0x42b6` -> `call 0xa80` (the carved name-lookup variant):
    (0x46AA, bytes.fromhex("e807fcffff"), bytes.fromhex("e8d1c3ffff")),

    # Carve a dedicated RAM segment at init. Data segments are full and init grabs
    # all remaining RAM for the heap (0x230f queries free RAM, 0x2318 allocs it ->
    # heap selector [0x1fe]). Trampoline that grab to leave a small block and alloc
    # it as a new segment, selector saved at EXE hole 0x9c2. Allocated last so no
    # existing selector shifts.
    #
    # Keep it small: int21/AH=48 allocs in 4 KB pages (ebx=8 => 32 KB), and the heap
    # scene-cache sits near the heap top (~0x22c000), so carving too much faults the
    # first dialogue.
    #
    # The carved seg holds ITEM.TOS, freeing the scene buffer at DATA_SEG:0xCC00 to
    # grow to 0xE000 (~5 KB). The fill+renderer already handle >2048 contiguously;
    # ITEM.TOS sitting at 0xD400 was the only cap (overrunning it corrupted item text).
    #
    # carve runs at 0x20ad, before the ITEM.TOS load stub at 0x215e, so the selector
    # exists by load time; load straight into carved:0. The item lookup variant scans
    # carved and copies the record (<=15 B) to DATA_SEG scratch 0x3ef2 so the shared
    # renderer (gs:[edx]) is untouched.
    #
    # trampoline @0x2318: (mov ah,48; int21; mov [0x1fe],ax; ret) -> jmp 0x9c4 + nops
    (0x2318, bytes.fromhex("b448" "cd21" "66a3fe010000" "c3"),
             bytes.fromhex("e9a7e6ffff" "909090909090")),
    # 0x9c2..0x9c3: carved-segment selector storage (stays 0; written at runtime).
    # carve stub @0x9c4: alloc a 32 KB carved seg (int21/AH=48 takes 4 KB PAGES, so
    # ebx=8 => 32 KB; keep small -- the heap scene-cache sits at the heap's top).
    (0x9C4, b"\x00" * 32, bytes.fromhex(
        "83eb08"          # sub ebx, 8             ; leave 8 pages (32 KB) for carved
        "b448" "cd21"     # alloc heap (avail-32KB) -> ax
        "66a3fe010000"    # mov [0x1fe], ax        ; heap selector (unchanged slot)
        "b448" "bb08000000" "cd21"   # alloc 8 pages (32 KB) carved -> ax
        "66a3c2090000"    # mov [0x9c2], ax        ; carved-segment selector
        "c3")),           # ret

    # ITEM.TOS boot-load stub @0x215e: load into carved:0 instead of DATA_SEG:0xD400.
    # mov bp,[0x1f6] -> mov bp,[0x9c2]   (load segment = carved)
    (0x215E, bytes.fromhex("668b2df6010000"), bytes.fromhex("668b2dc2090000")),
    # mov ebx,0xd400 -> mov ebx,0        (load offset 0)
    (0x2165, bytes.fromhex("bb00d40000"), bytes.fromhex("bb00000000")),

    # item-lookup variant @0xa03: scan ITEM.TOS in carved (ES=carved), copy the
    # Nth NUL-record (<=15 B) to DATA_SEG scratch 0x3ef2, return dx=0x3ef2 so the
    # shared renderer reads it via gs:[edx] unchanged.
    (0xA03, b"\x00" * 94, bytes.fromhex(
        "51565766" "068e05c2090000" "30d2" "83c308" "0fb7db" "3c02" "721d"
        "fec8" "88c4" "30c0" "31c9" "49" "87fb" "f2ae" "2666837ffe00" "7502"
        "fec2" "fecc" "75f0" "87fb" "89de" "bff23e0000" "b940000000"
        "268a06" "658807" "46" "47" "20c0" "7407" "49" "75f1" "65c60700"
        "baf23e0000" "6607" "5f" "5e" "59" "c3")),

    # item lookup @0x3c50: base 0xD400 -> 0 (carved offset 0)
    (0x3C50, bytes.fromhex("bb00d40000"), bytes.fromhex("bb00000000")),
    # @0x3c55: call 0x42b6 -> call the carved item-lookup variant @0xa03
    (0x3C55, bytes.fromhex("e85c060000"), bytes.fromhex("e8a9cdffff")),

    # Item names half-width. The renderer @0x42a4 reads width from bh ([0x2d3]:
    # 1=half, 2=full). General text is forced bh=1 above (0x448e/0x44a3), but the
    # item path (@0x3c55 -> render tail jmp 0x42a4 @0x3a74) keeps the caller's bh=2,
    # so long names ("Leather Armor") wrapped. Route that jmp through `mov bh,1` so
    # only item names go half (0x42a4 uses bh for width only, safe).
    # trampoline @0xa70 (runtime 0x870): mov bh,1 ; jmp 0x42a4
    (0xA70, b"\x00" * 7, bytes.fromhex("b701" "e92d3a0000")),
    # item render tail @0x3c74 (runtime 0x3a74): jmp 0x42a4 -> jmp 0x870 (trampoline)
    (0x3C74, bytes.fromhex("e92b080000"), bytes.fromhex("e9f7cdffff")),

    # Battle Auto/Manual value-box alignment @0xe574. The box-draw picks a start
    # column from the flag (gs:0xa032): one state col 0x0a, the other col 0x02,
    # width 8 cols. The half-width "[ Auto ][Manual]" text sits at cols 1-8 and
    # 9-16, so both box columns landed one cell too far right (Auto box over
    # cols 2-9, spilling into the "[" of Manual; Manual box over 10-17). Shift
    # both start columns left by 1 so each box wraps its word exactly.
    (0xE787, b"\x02", b"\x01"),  # Auto box col 2 -> 1
    (0xE77B, b"\x0A", b"\x09"),  # Manual box col 0xa -> 9
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
