"""Export the full game script: every dialogue string in every dlz block on the CD.

Output: script/<archive>.tsv with columns
  block_off   archive file offset of the dlz block
  str_off     offset of the string inside the decompressed block
  speaker     name-token at string start (box title), if any
  text        the line; newlines escaped as \\n

Usage: python tools/export_script.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import disc, dlz
from glodia.script import load_names, extract_strings

TRACK1_SECTORS = 2715
OUT = ROOT / "script"


def main():
    data_bin = (ROOT / "floppy_files" / "DATA.BIN").read_bytes()
    names = load_names(data_bin)
    iso = disc.extract_track1_iso(str(ROOT / "Vain DreamII (1993)(Glodia)(Jp).img"),
                                  TRACK1_SECTORS)
    OUT.mkdir(exist_ok=True)
    grand = 0
    for name in sorted(disc.list_files(iso)):
        if not name.endswith((".DAT", ".PK")):
            continue
        data = disc.read_file(iso, name)
        rows = []
        for pos, m in dlz.iter_members(data):
            try:
                block = dlz.decode_block(m)
            except ValueError:
                continue
            if block[:4] == b"PICT":        # image, not script
                continue
            for off, speaker, text in extract_strings(block, names):
                if text:
                    rows.append((pos, off, speaker or "", text))
        if rows:
            path = OUT / (name.replace(".", "_") + ".tsv")
            # preserve translator work: carry the `english` column across re-exports
            existing = {}
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines()[1:]:
                    cols = line.split("\t")
                    if len(cols) >= 5 and cols[4].strip():
                        existing[(cols[0], cols[1])] = cols[4]
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("block_off\tstr_off\tspeaker\ttext\tenglish\n")
                for pos, off, spk, text in rows:
                    eng = existing.get((f"{pos:#x}", f"{off:#x}"), "")
                    f.write(f"{pos:#x}\t{off:#x}\t{spk}\t"
                            + text.replace("\n", "\\n") + f"\t{eng}\n")
            print(f"{name:14s} {len(rows):5d} strings -> {path.name}")
            grand += len(rows)
        else:
            stale = OUT / (name.replace(".", "_") + ".tsv")
            stale.unlink(missing_ok=True)
            print(f"{name:14s}     0 strings")
    print(f"\nTOTAL {grand} strings")


if __name__ == "__main__":
    main()
