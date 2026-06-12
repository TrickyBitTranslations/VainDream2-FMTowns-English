"""Production grow build: apply ALL translations with NO per-scene budget.

Rebuilds every archive at natural member sizes, repoints the engine scene
tables in MAIN.EXP, and writes the archives to the CD — growing them in place
when they still fit their sector allocation, relocating into free disc sectors
(and updating the ISO directory record) when they don't.

Outputs the EN floppy + EN CD, same as build.ps1's CD step but unbounded.

Usage: python tools/grow_build.py [--demo]   (--demo also injects a long line)
"""
import pathlib, shutil, struct, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc, dlz
from glodia.floppy import read_d88
import grow, reinsert, patch_main_exp, patch_names, patch_items, patch_ui

BASE = "Vain DreamII (1993)(Glodia)(Jp)"
EN_D88 = ROOT / (BASE + "[SystemDisk]_EN.D88")
IMG = ROOT / (BASE + ".img")
EN_IMG = ROOT / (BASE + " [EN].img")
TRACK1_SECTORS = 2715
SEC = 2048
RAW = disc.RAW

# Decompressed-size budget. Dialogue scene blocks (tag "VD2*") get copied into a
# shared 2048-byte (0x800) display buffer at DATA_SEG:0xCC00, capped by ITEM.P
# right after it -- overrunning crashed the equipment menu. So dialogue blocks
# get a flat 2048 budget; anything else defaults to its original decompressed
# size. DECOMP_BUDGET holds per-block overrides if a specific block needs one.
# (A larger buffer needs the display-copy relocation -- see patch_main_exp.)
SCENE_BUFFER = 0x1380   # 4992: ITEM.TOS relocated to carved seg, buffer now 0xCC00..~0xE000
DECOMP_BUDGET = {}


# ---------- ISO geometry ----------
def iso_geometry(iso):
    """Return (pvd_vol_sectors, {name:(dir_rec_iso_off, lba, size)}, max_used_sec)."""
    pvd = iso[16 * SEC:17 * SEC]
    vol = struct.unpack("<I", pvd[80:84])[0]
    rlba = struct.unpack("<I", pvd[158:162])[0]
    rlen = struct.unpack("<I", pvd[166:170])[0]
    d = iso[rlba * SEC: rlba * SEC + rlen]
    recs = {}
    maxsec = 0
    i = 0
    while i < len(d):
        rl = d[i]
        if rl == 0:
            i = ((i // SEC) + 1) * SEC
            continue
        ext = struct.unpack("<I", d[i + 2:i + 6])[0]
        size = struct.unpack("<I", d[i + 10:i + 14])[0]
        nl = d[i + 32]
        nm = d[i + 33:i + 33 + nl].split(b";")[0].decode("latin1", "replace")
        recs[nm] = (rlba * SEC + i, ext, size)
        maxsec = max(maxsec, ext + (size + SEC - 1) // SEC)
        i += rl
    return vol, recs, maxsec


def raw_off(iso_off):
    sec, within = divmod(iso_off, SEC)
    return sec * RAW + SYNC(within)


def SYNC(within):
    return disc.SYNC_HEADER + within


# ---------- main ----------
def main(demo=False):
    iso = disc.extract_track1_iso(str(IMG), TRACK1_SECTORS)
    tokens = reinsert.name_token_map()
    rows = reinsert.load_rows()

    # validate every line up front so a typo'd {NAME} fails loudly with a
    # per-line message instead of hard-crashing mid-build (or worse, shipping a
    # half-written scene). Mirrors `reinsert.py --check`.
    errors = 0
    for archive, block_off, str_off, english, tsv_name, ln in rows:
        try:
            reinsert.compile_english(english, tokens)
        except (ValueError, KeyError) as e:
            print(f"ERROR  {tsv_name}:{ln}: {e}")
            errors += 1
    if errors:
        sys.exit(f"{errors} translation error(s) — fix the TSV and rebuild "
                 f"(run `python tools/reinsert.py --check` to re-validate)")

    per_arch = defaultdict(lambda: defaultdict(list))
    for archive, block_off, str_off, english, _, _ in rows:
        per_arch[archive][block_off].append((str_off, english))
    if demo:
        per_arch["VAIN_A.DAT"][0x5E8A8].append(
            (0x24, "Yawn... I could really go for a HUGE breakfast right now."))

    # rebuild each touched archive at natural sizes
    grown = {}                       # archive -> (new_bytes, old_offsets, new_offsets, old_size)
    decomp_errors = 0
    for archive, blocks in per_arch.items():
        data = disc.read_file(iso, archive)
        members = dict(dlz.iter_members(data))
        overrides = {}
        for block_off, lines in blocks.items():
            block = bytearray(dlz.decode(members[block_off], prefix=bytes(0x40000)))
            orig_decomp = len(block)
            for s_off, en in sorted(lines, reverse=True):
                a, b = reinsert.string_span(block, s_off)
                if reinsert.spans_event_code(block, a, b):   # mis-extracted into event code
                    print(f"  SKIP {archive}@{block_off:#x} str {s_off:#x}: "
                          f"original spans event bytecode (0x05-0x13) — unsafe to splice")
                    continue
                block[a:b] = reinsert.compile_english(en, tokens)
            # Decompressed-size budget. Dialogue blocks ("VD2*") share one fixed
            # 2048-byte RAM buffer; non-dialogue blocks keep their original size.
            # An override in DECOMP_BUDGET wins. (See SCENE_BUFFER note above.)
            is_dialogue = bytes(block[:3]) == b"VD2"
            budget = DECOMP_BUDGET.get((archive, block_off),
                                       SCENE_BUFFER if is_dialogue else orig_decomp)
            if len(block) > budget:
                print(f"ERROR  {archive}@{block_off:#x}: decompressed {len(block)} bytes "
                      f"> {budget}-byte RAM budget (over by {len(block) - budget}). The engine "
                      f"loads this block to a fixed address; growing it corrupts adjacent data "
                      f"(e.g. ITEM.P). Shorten the translation for this block.")
                decomp_errors += 1
            # Header fields the engine reads (dlz.encode doesn't set these right):
            #  - bytes 8..9: an opaque field; preserve the original's value.
            #  - bytes 10..12 (u24) = decompressed_size << 8. The engine uses this
            #    to reserve the block's RAM slot (rounded up to 0x800) before
            #    placing the next asset (ITEM.P) after it. It MUST reflect the NEW
            #    size, else the engine under-reserves and the grown block overruns
            #    ITEM.P -> equipment-menu crash. (Keeping the original size here was
            #    the bug; encode() zeroing it is also wrong.)
            enc = bytearray(dlz.encode(bytes(block)))
            enc[8:10] = members[block_off][8:10]
            nd = len(block)
            enc[10], enc[11], enc[12] = 0x00, nd & 0xFF, (nd >> 8) & 0xFF
            assert dlz.decode(bytes(enc), prefix=bytes(0x40000)) == bytes(block)
            overrides[block_off] = bytes(enc)
        old_offsets = list(members.keys())
        new_bytes, new_offsets = grow.rebuild(data, overrides)
        grown[archive] = (new_bytes, old_offsets, new_offsets, len(data))
        print(f"{archive}: {len(data)} -> {len(new_bytes)} bytes "
              f"({len(new_bytes)-len(data):+d})")

    if decomp_errors:
        sys.exit(f"{decomp_errors} block(s) exceed their decompressed RAM budget — "
                 f"shorten those translations and rebuild (these would corrupt the "
                 f"engine's memory and crash, e.g. the equipment menu).")

    # --- floppy: classifier + names + item names + repoint every grown archive's table ---
    patch_main_exp.main()    # JP -> EN_D88 reset + 1-byte-ASCII classifier patch
    patch_names.main()       # NAME.P (speaker/term inserts) in DATA.BIN
    patch_items.main(write=True)   # ITEM.TOS item names (literal kana/kanji runs)
    patch_ui.main(write=True)      # SYSTEM/SYSTEM2/FSYS .TOS UI/menu/system text
    fs = read_d88(EN_D88.read_bytes())
    from extract_floppy import read_file
    exe = read_file(fs, "MAIN.EXP")
    for archive, (nb, oo, no, osz) in grown.items():
        exe, _, ch = grow.patch_offset_table(exe, archive, oo, no, osz, len(nb))
        print(f"  floppy: {archive} table repointed ({ch} entries)")
    EN_D88.write_bytes(fs.patch_span(fs.flat_offset_for_file("MAIN.EXP", 0), exe))

    # --- CD: place grown archives, relocating as needed ---
    vol, recs, maxsec = iso_geometry(iso)
    # free regions (start_sec, n_sec): the end gap before track 2
    free = [(maxsec, TRACK1_SECTORS - maxsec)]
    placements = {}                  # archive -> (lba, new_bytes, dir_rec_off, new_size)
    # first pass: in-place where it fits, collect relocations
    relocate = []
    for archive, (nb, oo, no, osz) in grown.items():
        rec_off, lba, size = recs[archive]
        old_sec = (osz + SEC - 1) // SEC
        new_sec = (len(nb) + SEC - 1) // SEC
        if new_sec <= old_sec:
            placements[archive] = (lba, nb, rec_off, len(nb))
        else:
            free.append((lba, old_sec))     # free the old extent for reuse
            relocate.append((archive, nb, rec_off))
    # coalesce free, then first-fit the relocations (largest first)
    def alloc(n):
        free.sort()
        for idx, (st, ln) in enumerate(free):
            if ln >= n:
                free[idx] = (st + n, ln - n)
                return st
        raise RuntimeError(f"no free region for {n} sectors (need ISO track extension)")
    for archive, nb, rec_off in sorted(relocate, key=lambda x: -len(x[1])):
        n = (len(nb) + SEC - 1) // SEC
        lba = alloc(n)
        placements[archive] = (lba, nb, rec_off, len(nb))
        print(f"  CD: relocated {archive} -> LBA {lba} ({n} sectors)")

    shutil.copyfile(IMG, EN_IMG)
    new_maxsec = maxsec
    with open(EN_IMG, "r+b") as f:
        for archive, (lba, nb, rec_off, nsz) in placements.items():
            nsec = (nsz + SEC - 1) // SEC
            for i in range(nsec):
                chunk = nb[i * SEC:(i + 1) * SEC].ljust(SEC, b"\x00")
                f.seek((lba + i) * RAW + disc.SYNC_HEADER)
                f.write(chunk)
            # dir record: extent LBA (LE+BE) and size (LE+BE)
            r = raw_off(rec_off)
            f.seek(r + 2);  f.write(struct.pack("<I", lba) + struct.pack(">I", lba))
            f.seek(r + 10); f.write(struct.pack("<I", nsz) + struct.pack(">I", nsz))
            new_maxsec = max(new_maxsec, lba + nsec)
        # extend PVD volume size if we spilled past it
        if new_maxsec > vol:
            r = raw_off(16 * SEC + 80)
            f.seek(r); f.write(struct.pack("<I", new_maxsec) + struct.pack(">I", new_maxsec))
            print(f"  CD: PVD volume size {vol} -> {new_maxsec} sectors")

    # companion sheets so it mounts like the original
    cue = (ROOT / f"{BASE}.cue").read_text(encoding="utf-8", errors="replace")
    (ROOT / f"{BASE} [EN].cue").write_text(
        cue.replace(f"{BASE}.img", f"{BASE} [EN].img"), encoding="utf-8")
    for ext in (".ccd", ".sub"):
        src = ROOT / f"{BASE}{ext}"
        if src.exists():
            shutil.copyfile(src, ROOT / f"{BASE} [EN]{ext}")
    print(f"wrote {EN_IMG.name} (+ cue/ccd/sub) + {EN_D88.name}")


if __name__ == "__main__":
    main(demo="--demo" in sys.argv)
