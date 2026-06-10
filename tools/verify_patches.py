"""Post-build sanity check: assert every MAIN.EXP engine patch actually landed
in the built _EN.D88.

patch_main_exp.py asserts each patch while writing, but it can't catch a patch
that never *ran* (e.g. a stale-bytecode or write-race build importing an older
PATCHES list -- the remaining patches apply cleanly and the missing one is
silently skipped). Verifying the final artifact against PATCHES closes that gap.
Exits non-zero on any mismatch so the build fails loudly.
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from extract_floppy import read_file
import patch_main_exp

EN = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"


def main():
    exe = read_file(read_d88(EN.read_bytes()), "MAIN.EXP")
    bad = 0
    for off, _orig, repl in patch_main_exp.PATCHES:
        cur = exe[off:off + len(repl)]
        if cur != repl:
            print(f"  MISMATCH MAIN.EXP+{off:#x}: expected {repl.hex()} found {cur.hex()}")
            bad += 1
    if bad:
        sys.exit(f"{bad} engine patch(es) missing from the built floppy — stale build")
    print(f"  all {len(patch_main_exp.PATCHES)} engine patches verified in _EN.D88")


if __name__ == "__main__":
    main()
