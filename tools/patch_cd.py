"""Write a patched copy of the CD image with edited file bytes.

Maps (filename, offset-in-file, payload) onto the raw MODE1/2352 sectors of
track 1 and writes "<original> [EN].img" plus companion .cue (FILE rewritten)
and .ccd/.sub copies. The original LFS dump is never modified.

Note: sector EDC/ECC trailers are left stale - emulators don't verify them.

Usage: python tools/patch_cd.py        (applies extracted/vd2a01_patched.bin)
"""
import pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc

TRACK1_SECTORS = 2715
BASE = "Vain DreamII (1993)(Glodia)(Jp)"
EN = BASE + " [EN]"

def load_patches():
    """Prefer the reinsert.py manifest; fall back to the single-line PoC."""
    import json
    manifest = ROOT / "extracted" / "patches.json"
    if manifest.exists():
        return [(p["file"], p["offset"], ROOT / p["bin"])
                for p in json.loads(manifest.read_text())]
    return [("VAIN_A.DAT", 0x5E8A8, ROOT / "extracted" / "vd2a01_patched.bin")]


def raw_spans(file_lba, off, size):
    """Yield (img_offset, length, payload_offset) for a write into file bytes
    [off, off+size) across raw 2352-byte sectors (user data at +16, 2048 each)."""
    done = 0
    while done < size:
        pos = off + done
        lba = file_lba + pos // 2048
        in_sec = pos % 2048
        chunk = min(2048 - in_sec, size - done)
        yield lba * disc.RAW + disc.SYNC_HEADER + in_sec, chunk, done
        done += chunk


def main():
    img = ROOT / f"{BASE}.img"
    out_img = ROOT / f"{EN}.img"
    iso = disc.extract_track1_iso(str(img), TRACK1_SECTORS)
    entries = disc._entries(iso)

    print(f"copying image -> {out_img.name} (~{img.stat().st_size >> 20} MB)")
    shutil.copyfile(img, out_img)

    with open(out_img, "r+b") as f:
        for name, off, payload_path in load_patches():
            payload = payload_path.read_bytes()
            lba, fsize = entries[name]
            assert off + len(payload) <= fsize, "patch exceeds file extent"
            for img_off, length, src_off in raw_spans(lba, off, len(payload)):
                f.seek(img_off)
                f.write(payload[src_off:src_off + length])
            print(f"  {name}+{off:#x}: {len(payload)} bytes "
                  f"({(len(payload) + 2047) // 2048 + 1} sectors touched)")

    # companion sheets so it mounts exactly like the original
    cue = (ROOT / f"{BASE}.cue").read_text(encoding="utf-8", errors="replace")
    (ROOT / f"{EN}.cue").write_text(cue.replace(f"{BASE}.img", f"{EN}.img"),
                                    encoding="utf-8")
    ccd = ROOT / f"{BASE}.ccd"
    sub = ROOT / f"{BASE}.sub"
    if ccd.exists():
        shutil.copyfile(ccd, ROOT / f"{EN}.ccd")
    if sub.exists():
        shutil.copyfile(sub, ROOT / f"{EN}.sub")
    print(f"wrote {EN}.img / .cue / .ccd / .sub")


if __name__ == "__main__":
    main()
