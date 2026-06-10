"""Extract files from Track 1 (MODE1/2352) ISO9660 of the Vain Dream II CD."""
import struct

RAW = 2352   # bytes per raw sector on disc
USER = 2048  # ISO9660 logical sector size
SYNC_HEADER = 16  # 12-byte sync + 4-byte header before user data in MODE1/2352


def extract_track1_iso(img_path, track1_sectors):
    """Read the data track and strip raw-sector framing -> a flat ISO9660 image."""
    with open(img_path, "rb") as f:
        raw = f.read(RAW * track1_sectors)
    out = bytearray()
    for i in range(track1_sectors):
        sec = raw[i * RAW:(i + 1) * RAW]
        out += sec[SYNC_HEADER:SYNC_HEADER + USER]
    return bytes(out)


def _sector(iso, n):
    return iso[n * USER:(n + 1) * USER]


def _root_record(iso):
    pvd = _sector(iso, 16)
    return pvd[156:156 + 34]


def _parse_dir(iso, lba, length):
    data = iso[lba * USER: lba * USER + length]
    i = 0
    out = []
    while i < len(data):
        rec_len = data[i]
        if rec_len == 0:
            # records never span sectors; jump to next sector boundary
            i = ((i // USER) + 1) * USER
            if i >= len(data):
                break
            continue
        rec = data[i:i + rec_len]
        ext_lba = struct.unpack("<I", rec[2:6])[0]
        size = struct.unpack("<I", rec[10:14])[0]
        flags = rec[25]
        name_len = rec[32]
        name = rec[33:33 + name_len]
        out.append((name, ext_lba, size, flags))
        i += rec_len
    return out


def _entries(iso):
    root = _root_record(iso)
    lba = struct.unpack("<I", root[2:6])[0]
    length = struct.unpack("<I", root[10:14])[0]
    files = {}
    for name, ext_lba, size, flags in _parse_dir(iso, lba, length):
        if flags & 0x02:           # directory
            continue
        if name in (b"\x00", b"\x01"):  # . and ..
            continue
        clean = name.split(b";", 1)[0].decode("latin1")  # drop ;1 version suffix
        files[clean] = (ext_lba, size)
    return files


def list_files(iso):
    return list(_entries(iso).keys())


def read_file(iso, name):
    ext_lba, size = _entries(iso)[name]
    return iso[ext_lba * USER: ext_lba * USER + size]
