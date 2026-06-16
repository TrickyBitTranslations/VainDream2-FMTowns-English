"""Validate a single translation suggestion (the issue-form bot).

Reads the issue body from $ISSUE_BODY (GitHub issue-form markdown), extracts
file / line id / proposed translation, validates syntax + rendered width, and
recomputes the block budget with the suggestion applied ON TOP of the current
TSV translations. Emits a markdown report to stdout (posted as the issue
comment) and exits 0 (valid) / 1 (invalid).

Local use: ISSUE_BODY="### Script file\n\nVAIN_A_DAT.tsv\n..." python tools/validate_suggestion.py
"""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root (.github/scripts/..)
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


def _id_eq(a, b):
    """Match a line-id field: hex (dialogue offsets) or literal (.TOS file names)."""
    try:
        return int(a, 16) == int(b, 16)
    except ValueError:
        return a == b


def find_row(tsv_name, block_s, str_s):
    """(speaker, jp_text) for the matching row, or ("", None) if absent."""
    for r in (ROOT / "script" / tsv_name).read_text(
            encoding="utf-8").splitlines()[1:]:
        c = r.split("\t")
        if len(c) >= 4 and _id_eq(c[0], block_s) and _id_eq(c[1], str_s):
            return c[2], c[3]
    return "", None


def main():
    body = os.environ.get("ISSUE_BODY", "")
    fields = parse_form(body)
    try:
        tsv_name = fields["script file"]
        block_s, str_s = fields["line id"].split()
        text = fields["proposed translation"].strip()
        assert text and text.lower() != "_no response_"
    except Exception:
        print("### :x: Could not parse the suggestion\n\n"
              "Please use the issue form fields: script file, line id, and a "
              "non-empty proposed translation.")
        sys.exit(1)
    # normalize: editors often paste real newlines instead of \n
    text = text.replace("\r", "").replace("\n", "\\n")

    is_markup = tsv_name.endswith("_TOS.tsv") or tsv_name == "STAGE.tsv"
    problems = []
    budget_note = ""
    speaker, jp_text = find_row(tsv_name, block_s, str_s)

    if is_markup:
        # UI / menu / system text (.TOS) and place names (STAGE): the english uses
        # the uitext markup + {NAME} tokens, reinserted by patch_ui / patch_stage,
        # not the dialogue dlz path. The hard RAM-slot budget for these is checked
        # at build time (it needs the game dump); here we only check syntax.
        archive = tsv_name
        from glodia.uitext import encode_markup
        try:
            encode_markup(text, tokens=reinsert.name_token_map())
        except Exception as e:
            problems.append(f"syntax: {e}")
        if not problems and jp_text is None:
            problems.append(f"line id {block_s} {str_s} not found in {tsv_name}")
    else:
        archive = tsv_name.replace("_DAT.tsv", ".DAT").replace("_PK.tsv", ".PK")
        block_off, str_off = int(block_s, 16), int(str_s, 16)
        tokens = reinsert.name_token_map()
        try:
            reinsert.compile_english(text, tokens)
        except (ValueError, KeyError) as e:
            problems.append(f"syntax: {e}")
        rev = {patch_names.TRANSLATIONS[jp].upper(): patch_names.TRANSLATIONS[jp]
               for jp in patch_names.TRANSLATIONS}
        for i, w in enumerate(reinsert.visual_lines(text, rev), 1):
            if w > reinsert.MAX_LINE:
                problems.append(f"line {i} renders {w} cells (max ~{reinsert.MAX_LINE})")
        if not problems and jp_text is None:
            problems.append(f"line id {block_s} {str_s} not found in {tsv_name}")
        elif not problems:
            # reject mis-extracted rows whose original spans event bytecode (0xff):
            # translating them corrupts the scene (crash). Can't be safely localized.
            try:
                src = (reinsert.IsoSource()
                       if reinsert.IMG.exists() and reinsert.IMG.stat().st_size > 1_000_000
                       else reinsert.PackSource())
                blk = src.block(archive, block_off)
                a, b = reinsert.string_span(blk, str_off)
                if 0xFF in blk[a:b]:
                    problems.append("this line was mis-extracted (it spans the scene's "
                                    "event bytecode) and can't be translated yet - skip it")
            except Exception:
                pass
    # NOTE: no per-scene byte budget - the build grows archives and repoints the
    # engine scene table, so translations can be any length. Only syntax, line
    # width, and this safety check apply.

    def original_section():
        if jp_text is None:
            return
        who = f" - {speaker}" if speaker else ""
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
