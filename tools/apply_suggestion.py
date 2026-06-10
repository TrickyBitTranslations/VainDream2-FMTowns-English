"""Apply a validated translation suggestion to its TSV row (the /apply bot).

Reads the issue body from $ISSUE_BODY (same form as validate_suggestion.py)
and writes the proposed translation into the english column of the matching
row in script/<file>. Run validate_suggestion.py first; this tool only edits
the spreadsheet.

Prints a one-line summary; exits 1 if the row can't be found.
"""
import os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from validate_suggestion import parse_form


def main():
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    tsv_name = fields["script file"]
    block_s, str_s = fields["line id"].split()
    text = fields["proposed translation"].strip()
    text = text.replace("\r", "").replace("\n", "\\n")

    path = ROOT / "script" / tsv_name
    lines = path.read_text(encoding="utf-8").splitlines()
    out = [lines[0]]
    hit = False
    for line in lines[1:]:
        c = line.split("\t")
        if (len(c) >= 4 and c[0].startswith("0x")
                and int(c[0], 16) == int(block_s, 16)
                and int(c[1], 16) == int(str_s, 16)):
            while len(c) < 5:
                c.append("")
            c[4] = text
            hit = True
            line = "\t".join(c)
        out.append(line)
    if not hit:
        print(f"row {block_s} {str_s} not found in {tsv_name}")
        sys.exit(1)
    path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"applied to {tsv_name} row {block_s} {str_s}")


if __name__ == "__main__":
    main()
