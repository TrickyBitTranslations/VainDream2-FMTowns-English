"""Validate a single translation suggestion (the issue-form bot).

Reads the issue body from $ISSUE_BODY (GitHub issue-form markdown), extracts
file / line id / proposed translation, validates syntax + rendered width, and
recomputes the block budget with the suggestion applied ON TOP of the current
TSV translations. Emits a markdown report to stdout (posted as the issue
comment) and exits 0 (valid) / 1 (invalid).

Local use: ISSUE_BODY="### Script file\n\nVAIN_A_DAT.tsv\n..." python tools/validate_suggestion.py
"""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import dlz
import patch_names
import reinsert


def parse_form(body):
    """{heading: value} from issue-form markdown (### Heading\\n\\nvalue)."""
    fields = {}
    for m in re.finditer(r"^### (.+?)\s*\n+(.*?)(?=\n### |\Z)", body,
                         re.S | re.M):
        fields[m.group(1).strip().lower()] = m.group(2).strip()
    return fields


def main():
    body = os.environ.get("ISSUE_BODY", "")
    fields = parse_form(body)
    try:
        tsv_name = fields["script file"]
        block_s, str_s = fields["line id"].split()
        block_off, str_off = int(block_s, 16), int(str_s, 16)
        text = fields["proposed translation"].strip()
        assert text and text.lower() != "_no response_"
    except Exception:
        print("### :x: Could not parse the suggestion\n\n"
              "Please use the issue form fields: script file, line id "
              "(`0x... 0x...`), and a non-empty proposed translation.")
        sys.exit(1)
    # normalize: editors often paste real newlines instead of \n
    text = text.replace("\r", "").replace("\n", "\\n")

    archive = tsv_name.replace("_DAT.tsv", ".DAT").replace("_PK.tsv", ".PK")
    tokens = reinsert.name_token_map()
    problems = []

    try:
        reinsert.compile_english(text, tokens)
    except (ValueError, KeyError) as e:
        problems.append(f"syntax: {e}")

    rev = {patch_names.TRANSLATIONS[jp].upper(): patch_names.TRANSLATIONS[jp]
           for jp in patch_names.TRANSLATIONS}
    for i, w in enumerate(reinsert.visual_lines(text, rev), 1):
        if w > reinsert.MAX_LINE:
            problems.append(f"line {i} renders {w} cells (max ~{reinsert.MAX_LINE})")

    # locate the line in the TSV: validates the id AND gives us the Japanese
    jp_text = None
    speaker = ""
    for r in (ROOT / "script" / tsv_name).read_text(encoding="utf-8").splitlines()[1:]:
        c = r.split("\t")
        if (len(c) >= 4 and c[0].startswith("0x")
                and int(c[0], 16) == block_off and int(c[1], 16) == str_off):
            speaker, jp_text = c[2], c[3]
            break

    budget_note = ""
    if not problems:
        # block budget: current TSV translations, with this suggestion applied
        rows = [(s, e) for a, b, s, e, _, _ in reinsert.load_rows()
                if a == archive and b == block_off]
        merged = {s: e for s, e in rows}
        if jp_text is None:
            problems.append(f"line id {block_s} {str_s} not found in {tsv_name}")
        else:
            merged[str_off] = text
            src = (reinsert.IsoSource()
                   if reinsert.IMG.exists() and reinsert.IMG.stat().st_size > 1_000_000
                   else reinsert.PackSource())
            block = src.block(archive, block_off)
            for s, e in sorted(merged.items(), reverse=True):
                start, end = reinsert.string_span(block, s)
                block[start:end] = reinsert.compile_english(e, tokens)
            used = len(dlz.encode(bytes(block)))
            budget = src.budget(archive, block_off)
            if used > budget:
                problems.append(
                    f"scene budget: {used - budget} bytes over "
                    f"({used}/{budget}) with this suggestion applied - "
                    f"shorten it (or other lines in block {block_s})")
            else:
                budget_note = (f"\nScene budget with this applied: "
                               f"**{used}/{budget} bytes ({budget - used} free)**")

    def original_section():
        if jp_text is None:
            return
        who = f" — {speaker}" if speaker else ""
        print(f"\n**Original**{who}:\n")
        print("> " + jp_text.replace("\\n", "<br>"))

    if problems:
        print("### :x: Suggestion has problems\n")
        for p in problems:
            print(f"- {p}")
        original_section()
        print("\nSee CONTRIBUTING.md for syntax and budget rules. "
              "Edit the issue to re-run validation.")
        sys.exit(1)
    print("### :white_check_mark: Suggestion is valid\n")
    print(f"`{archive}` block `{block_s}` line `{str_s}`:\n")
    print("```")
    print(text.replace("\\n", "\n").replace("\\p", "\n--- page ---\n"))
    print("```")
    original_section()
    print(budget_note)
    print("\nA maintainer can apply it with a `/apply` comment, or by pasting "
          "the text into the TSV row.")


if __name__ == "__main__":
    main()
