"""PROOF: grow the wake-up scene PAST its compressed budget and ship bootable
media, by rebuilding the archive + repointing the engine's scene table.

Produces the EN floppy (classifier + names + repointed VAIN_A table) and the
EN CD (grown VAIN_A written in place - the demo grow still fits VAIN_A's 242
sector allocation, so no relocation; that is the next step). If the wake-up
scene shows the long line and later scenes still play, the per-scene budget
is gone.

Usage: python tools/grow_demo.py
"""
import pathlib, shutil, struct, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc, dlz
from glodia.floppy import read_d88
from collections import defaultdict
import grow, reinsert, patch_main_exp, patch_names

BASE = "Vain DreamII (1993)(Glodia)(Jp)"
EN_D88 = ROOT / (BASE + "[SystemDisk]_EN.D88")
IMG = ROOT / (BASE + ".img")
EN_IMG = ROOT / (BASE + " [EN].img")
TRACK1_SECTORS = 2715
WOFF = 0x5E8A8
LONG = ("Yawn... I could really go for a HUGE breakfast right about now,\\n"
        "the kind with eggs and toast and all the works.\\n"
        "What are we having today, anyway?")


def read_exe(fs):
    from extract_floppy import read_file
    return read_file(fs, "MAIN.EXP")


def main():
    iso = disc.extract_track1_iso(str(IMG), TRACK1_SECTORS)
    vain_a = disc.read_file(iso, "VAIN_A.DAT")
    members = dict(dlz.iter_members(vain_a))
    tokens = reinsert.name_token_map()

    # all VAIN_A translations from the TSV (so moved scenes show real English),
    # grouped by block; the wake-up block also gets the long over-budget line
    by_block = defaultdict(list)
    for archive, block_off, str_off, english, _, _ in reinsert.load_rows():
        if archive == "VAIN_A.DAT":
            by_block[block_off].append((str_off, english))
    by_block[WOFF].append((0x24, LONG))

    overrides = {}
    for block_off, lines in by_block.items():
        block = bytearray(dlz.decode(members[block_off], prefix=bytes(0x40000)))
        for str_off, english in sorted(lines, reverse=True):
            s, e = reinsert.string_span(block, str_off)
            block[s:e] = reinsert.compile_english(english, tokens)
        # preserve original header bytes 8..12 (decomp field + dest RAM addr);
        # encode() zeros dest_addr, which the engine's scene loader honours (see grow_build.py)
        enc = bytearray(dlz.encode(bytes(block)))
        enc[8:13] = members[block_off][8:13]
        overrides[block_off] = bytes(enc)

    wm = overrides[WOFF]
    print(f"wake-up member: {len(members[WOFF])} -> {len(wm)} bytes "
          f"(old budget {len(members[WOFF])}; +{len(wm)-len(members[WOFF])} over)")

    old_offsets = [o for o, _ in dlz.iter_members(vain_a)]
    new_vain_a, new_offsets = grow.rebuild(vain_a, overrides)
    old_size, new_size = len(vain_a), len(new_vain_a)

    lba, dir_size = disc._entries(iso)["VAIN_A.DAT"]
    old_sectors = (old_size + 2047) // 2048
    new_sectors = (new_size + 2047) // 2048
    assert new_sectors <= old_sectors, (
        f"demo grow needs relocation ({new_sectors}>{old_sectors} sectors) - "
        f"that's the next step")
    print(f"VAIN_A {old_size} -> {new_size} bytes, fits {old_sectors} sectors (in place)")

    # --- floppy: normal EN build, then repoint VAIN_A's scene table ---
    patch_main_exp.main()
    patch_names.main()
    fs = read_d88(EN_D88.read_bytes())
    exe, n, changed = grow.patch_offset_table(
        read_exe(fs), "VAIN_A.DAT", old_offsets, new_offsets, old_size, new_size)
    flat = fs.flat_offset_for_file("MAIN.EXP", 0)
    EN_D88.write_bytes(fs.patch_span(flat, exe))
    print(f"floppy: repointed VAIN_A table ({changed} entries), wrote {EN_D88.name}")

    # --- CD: copy, write grown VAIN_A in place, update its dir-record size ---
    shutil.copyfile(IMG, EN_IMG)
    with open(EN_IMG, "r+b") as f:
        # member file bytes -> raw 2352 sectors (2048 user data each)
        for i in range(new_sectors):
            chunk = new_vain_a[i * 2048:(i + 1) * 2048]
            sec = lba + i
            f.seek(sec * disc.RAW + disc.SYNC_HEADER)
            f.write(chunk.ljust(2048, b"\x00"))
        # update directory record size (both LE and BE u32 in ISO9660)
        rec_iso = _dir_record_offset(iso, "VAIN_A.DAT")
        raw = _iso_to_raw(rec_iso)
        f.seek(raw + 10)
        f.write(struct.pack("<I", new_size) + struct.pack(">I", new_size))
    print(f"CD: wrote grown VAIN_A.DAT + updated dir size, {EN_IMG.name}")
    print("\nBoot _EN.D88 + [EN].img: the wake-up box should show the long line, "
          "and later scenes must still play.")


def _dir_record_offset(iso, name):
    pvd = iso[16 * 2048:17 * 2048]
    rlba = struct.unpack("<I", pvd[158:162])[0]
    rlen = struct.unpack("<I", pvd[166:170])[0]
    d = iso[rlba * 2048: rlba * 2048 + rlen]
    i = 0
    while i < len(d):
        rl = d[i]
        if rl == 0:
            i = ((i // 2048) + 1) * 2048
            continue
        nl = d[i + 32]
        nm = d[i + 33:i + 33 + nl].split(b";")[0].decode("latin1", "replace")
        if nm == name:
            return rlba * 2048 + i
        i += rl
    raise KeyError(name)


def _iso_to_raw(iso_off):
    sec, within = divmod(iso_off, 2048)
    return sec * disc.RAW + disc.SYNC_HEADER + within


if __name__ == "__main__":
    main()
