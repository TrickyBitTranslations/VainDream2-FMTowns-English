"""Apply a name/term suggestion (the /apply bot for name-suggestion issues).

Reads $ISSUE_BODY, extracts the Japanese term and the proposed English, and
updates the TRANSLATIONS table in tools/patch_names.py. Before writing, it
budget-checks the name table: the rewritten span (records 1..last-translated)
must fit its original byte total - placeholder records absorb slack, English
is 1 byte/char (+1 per apostrophe).

The change reaches the game on the next floppy build (build.ps1 -Full).
Exits 0 (applied) / 1 (rejected, reason on stdout).
"""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import reinsert
from validate_suggestion import parse_form

NAMES_TSV = ROOT / "script" / "NAMES.tsv"
PLACEHOLDER = "未使用"


def en_bytes(en):
    return len(en) + en.count("'")          # apostrophe is a 2-byte glyph


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    try:
        term = fields["term"]
        proposed = fields["proposed english"].strip()
        assert proposed and proposed.lower() != "_no response_"
    except Exception:
        print("Could not parse the suggestion (need Term and Proposed English).")
        sys.exit(1)
    jp = re.sub(r"\s*\(token .*?\)\s*$", "", term).strip()
    try:
        proposed.encode("ascii")
        bad = set(proposed) - set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,!?-'")
        assert not bad
    except Exception:
        print(f"Proposed name has unsupported characters for the 1-byte charset.")
        sys.exit(1)

    pack = reinsert.load_pack()
    jp_names = pack.get("jp_names", {})
    jp_lens = pack.get("jp_lens", {})
    tok = next((int(t) for t, j in jp_names.items() if j == jp), None)
    if tok is None:
        print(f"Term {jp!r} not found in the name table.")
        sys.exit(1)

    # NOTE: no name-table byte budget anymore - the build grows DATA.BIN on the
    # floppy (FAT12) to fit the whole table, so romanizations can be any length.
    # Only the charset (checked above) and the term existing matter.
    # The names live in script/NAMES.tsv (the single source patch_names loads).
    so = f"{tok:#x}"
    rows = NAMES_TSV.read_text(encoding="utf-8").splitlines()
    hit = False
    for i, row in enumerate(rows[1:], start=1):
        c = row.split("\t")
        if len(c) >= 5 and c[1] == so:
            c[4] = proposed
            rows[i] = "\t".join(c[:5])
            hit = True
            break
    assert hit, f"token {so} not found in NAMES.tsv"
    NAMES_TSV.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"Set {jp} -> {proposed} (token {so}) in NAMES.tsv. "
          f"Takes effect in the next floppy build.")


if __name__ == "__main__":
    main()
