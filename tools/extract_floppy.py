"""Extract files from the boot floppy D88 into floppy_files/ (derived, gitignored).

Usage: python tools/extract_floppy.py [NAME ...]   (no args = list root directory)
"""
import pathlib, struct, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import D88

D88_PATH = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88"
OUT = ROOT / "floppy_files"


def list_root(fs):
    b, ss, _, root_start, _ = fs._layout()
    out = []
    for i in range(b["rootent"]):
        e = fs.flat[root_start + i * 32: root_start + i * 32 + 32]
        if e[0] == 0:
            break
        if e[0] == 0xE5 or (e[11] & 0x08) or (e[11] & 0x10):
            continue
        nm = e[0:8].decode("latin1").rstrip()
        ext = e[8:11].decode("latin1").rstrip()
        size = struct.unpack("<I", e[28:32])[0]
        out.append((nm + ("." + ext if ext else ""), size))
    return out


def read_file(fs, name):
    clu, size = fs._dir_entry(name)
    b, ss, *_ = fs._layout()
    csize = b["spc"] * ss
    data = bytearray()
    for c in fs._cluster_chain(clu):
        off = fs._cluster_flat_offset(c)
        data += fs.flat[off:off + csize]
    return bytes(data[:size])


if __name__ == "__main__":
    fs = D88(D88_PATH.read_bytes())
    if len(sys.argv) < 2:
        for name, size in list_root(fs):
            print(f"{size:9d}  {name}")
    else:
        OUT.mkdir(exist_ok=True)
        for name in sys.argv[1:]:
            data = read_file(fs, name)
            (OUT / name).write_bytes(data)
            print(f"wrote floppy_files/{name} ({len(data)} bytes)")
