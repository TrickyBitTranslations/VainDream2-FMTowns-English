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
    # 1 = half-cell advance + condensed glyphs.
    (0x448E, b"\x02", b"\x01"),
    (0x44A3, b"\x02", b"\x01"),
    # ...but `<03 03>` is a per-string width TOGGLE (handler @0x4622 flips [0x2d3]
    # 1<->2). In the stock game (full-width default) it meant "make this span HALF".
    # Flipping the default above INVERTED it: every record still carrying <03 03>
    # (currency "Dain"/"Themis", status "Level", the hit-count "times.") now toggled
    # to FULL-width and overflowed its field -- the trailing glyph wrapped to col 0 of
    # the next line ("Dain"->"Dai" + an orphan "n", "Themis"->"Them"), and in the shop
    # buy list the wrapped "n" corrupted the item-icon column. Pin the op to its
    # original intent -- ALWAYS set half -- by making the half->full branch also write
    # 1 (imm 0x02->0x01 at the `mov [0x2d3],2` @0x4635). Live-verified: buy list prices
    # + money box ("980 Dain" / "0 Themis") render full and fit; icons clean.
    (0x4835, b"\x02", b"\x01"),

    # --- Name-table relocation (step 2): the FULL untrimmed NAME.P table now rides in
    # ITEM.TOS and loads into the carved segment at carved:0x2000 (see patch_items),
    # freeing names from DATA.BIN's RAM-bounded cap. The char-name handler @0x46aa is
    # repointed at a name-lookup VARIANT that mirrors the item variant: scan carved
    # (ES=[0x9c2]) for the Nth NUL-record and COPY it to a low DATA_SEG scratch (0x3f40),
    # returning that low offset -- so the shared renderer's `movzx edx,dx; mov gs:[edx]`
    # reads the low scratch and never hits the 16-bit barrier (which is exactly why a
    # naive high-address move failed before -- the renderer truncates the offset).
    #
    # name-lookup variant @0xa80 = the item variant (@0xa03) with its scratch 0x3ef2 ->
    # 0x3f40 (the item record sits in 0x3ef2 while ITS own ⟨02 nn⟩ name token renders):
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

    # --- Carve a dedicated RAM segment at init (reusable home for future
    # scene-buffer / name-table relocation). The data segments are full and init
    # grabs ALL remaining RAM for the heap (query-then-grab: 0x230f queries free
    # RAM into ebx, 0x2318 allocs it -> heap selector at [0x1fe]). Trampoline the
    # grab so it leaves a small block and allocates that as a fresh segment whose
    # selector is saved at EXE hole word 0x9c2. The carved segment is allocated
    # LAST so no existing selector number shifts.
    #
    # NOTE: int21/AH=48 allocates in 4 KB PAGES here (ebx=8 => 32 KB), NOT
    # paragraphs. Keep it small: the engine puts a scene cache near the TOP of the
    # heap (~heap offset 0x22c000), so carving more than a little off the heap's
    # tail pushes that cache past the heap limit and faults on the first dialogue.
    #
    # The carved segment holds ITEM.TOS, freeing the scene buffer at DATA_SEG:0xCC00
    # to grow contiguously up to the next struct at 0xE000 (~5 KB). Proven by
    # experiment: the scene fill + renderer already handle >2048 contiguously; the
    # ONLY cap was ITEM.TOS sitting at 0xD400 (overrunning it corrupted item text).
    # So we move ITEM.TOS out of the way and leave the buffer/fill/renderer untouched.
    #
    # The heap setup (carve) is called at 0x20ad, BEFORE the ITEM.TOS file-load stub
    # at 0x215e -- so the carved selector exists by load time and we load ITEM.TOS
    # straight into carved:0 (repoint the load stub). It's read through one lookup
    # (0x3c55 -> 0x42b6); the shared string renderer derefs the record via gs:[edx]
    # (=DATA_SEG), so the item lookup variant scans carved and copies the found
    # record (<=15 B) into a free DATA_SEG scratch (0x3ef2) -- renderer untouched.
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

    # --- item names half-width. The shared string renderer @0x42a4 takes the width
    # from BH ([0x2d3]: 1=half, 2=full). General-text entries are forced to bh=1
    # above (0x448e/0x44a3), but the ITEM path (lookup @0x3c55 -> the render tail
    # `jmp 0x42a4` @0x3a74) keeps the CALLER's bh=2, so long names ("Leather Armor")
    # wrapped. Verified live: at 0x3a74, edx=0x3ef2 (item scratch), ebx=0x0204 (bh=2).
    # Trampoline that JMP through `mov bh,1` so ONLY item names go half-width
    # (0x42a4 zeroes BL itself and uses BH only for width -> safe).
    # trampoline @0xa70 (runtime 0x870): mov bh,1 ; jmp 0x42a4
    (0xA70, b"\x00" * 7, bytes.fromhex("b701" "e92d3a0000")),
    # item render tail @0x3c74 (runtime 0x3a74): jmp 0x42a4 -> jmp 0x870 (trampoline)
    (0x3C74, bytes.fromhex("e92b080000"), bytes.fromhex("e9f7cdffff")),
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
