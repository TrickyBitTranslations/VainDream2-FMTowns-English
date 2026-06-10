"""Apply a name/term suggestion (the /apply bot for name-suggestion issues).

Reads $ISSUE_BODY, extracts the Japanese term and the proposed English, and
updates the TRANSLATIONS table in tools/patch_names.py. Before writing, it
budget-checks the name table: the rewritten span (records 1..last-translated)
must fit its original byte total — placeholder records absorb slack, English
is 1 byte/char (+1 per apostrophe).

The change reaches the game on the next floppy build (build.ps1 -Full).
Exits 0 (applied) / 1 (rejected, reason on stdout).
"""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import reinsert
from validate_suggestion import parse_form

PN = ROOT / "tools" / "patch_names.py"
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

    import patch_names
    new_map = dict(patch_names.TRANSLATIONS)
    new_map[jp] = proposed

    # budget: rewritten span = records 1..max translated token
    toks = {j: int(t) for t, j in jp_names.items()}
    hit_toks = [toks[j] for j in new_map if j in toks and j != PLACEHOLDER]
    span_end = max(hit_toks)
    orig = new = 0
    missing = []
    for t in range(1, span_end + 1):
        raw_len = jp_lens.get(str(t))
        if raw_len is None:
            missing.append(t)
            continue
        orig += raw_len
        j = jp_names.get(str(t), "")
        if j == PLACEHOLDER:
            new += 0                          # placeholders shrink to empty
        elif j in new_map:
            new += en_bytes(new_map[j])
        else:
            new += raw_len
    if missing:
        print(f"Cannot budget-check (records {missing} not in the pack) — "
              f"apply manually with the game data.")
        sys.exit(1)
    if new > orig:
        print(f"Name table budget: {new - orig} bytes over "
              f"({new}/{orig} for records 1..{span_end}) — needs a shorter name "
              f"or freeing other entries.")
        sys.exit(1)

    src = PN.read_text(encoding="utf-8")
    line = f'    "{jp}": "{proposed}",'
    pat = re.compile(r'^    "' + re.escape(jp) + r'": ".*?",.*$', re.M)
    if pat.search(src):
        src = pat.sub(line, src, count=1)
    else:
        anchor = f'    "{PLACEHOLDER}":'
        assert anchor in src, "placeholder anchor missing in patch_names.py"
        src = src.replace(anchor, line + "\n" + anchor, 1)
    PN.write_text(src, encoding="utf-8", newline="\n")
    print(f"Set {jp} -> {proposed} (token 0x{tok:02x}). "
          f"Name table at {new}/{orig} bytes for the rewritten span. "
          f"Takes effect in the next floppy build.")


if __name__ == "__main__":
    main()
