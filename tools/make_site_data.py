"""Generate the static JSON the website reads (site/data/*.json).

  script.json       every line: ids, speaker, japanese, english
  status.json       progress totals + per-block byte budgets
  suggestions.json  open suggestion issues mapped to line ids (optional;
                    pass --issues <file> with the GitHub API JSON)

Run by the Pages deploy workflow; works without the game dump (blockpack).

Usage: python tools/make_site_data.py [--issues issues.json]
"""
import json, pathlib, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia import dlz
import reinsert
from validate_suggestion import parse_form

OUT = ROOT / "site" / "data"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    issues_path = None
    if "--issues" in sys.argv:
        issues_path = pathlib.Path(sys.argv[sys.argv.index("--issues") + 1])

    # ---- script.json + per-file/block tallies --------------------------------
    import re as _re

    def is_engine_data(jp):
        """Extraction noise that crossed into event bytecode — not translatable."""
        return ("⟨" in jp or jp.startswith("。")
                or _re.search(r"(\\n){3,}", jp) is not None)

    src_blocks = (reinsert.IsoSource()
                  if reinsert.IMG.exists() and reinsert.IMG.stat().st_size > 1_000_000
                  else reinsert.PackSource())

    def is_script_block(archive, block_s):
        """Real scene blocks open with an ASCII tag (VD2A01, A01_, ...);
        binary data blocks (stats tables etc.) don't — their 'strings' are
        numeric bytes misread as name tokens."""
        try:
            head = bytes(src_blocks.block(archive, int(block_s, 16))[:4])
        except Exception:
            return True
        ok = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        return all(b in ok for b in head)

    files = {}
    tally = defaultdict(lambda: {"lines": 0, "done": 0})
    per_block_rows = defaultdict(list)
    for tsv in sorted((ROOT / "script").glob("*.tsv")):
        archive = tsv.name.replace("_DAT.tsv", ".DAT").replace("_PK.tsv", ".PK")
        blocks = defaultdict(list)
        script_block = {}
        for row in tsv.read_text(encoding="utf-8").splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 4 or not c[0].startswith("0x"):
                continue
            if c[0] not in script_block:
                script_block[c[0]] = is_script_block(archive, c[0])
            en = c[4].strip() if len(c) >= 5 else ""
            line = {"id": c[1], "sp": c[2], "jp": c[3], "en": en}
            if not script_block[c[0]] or is_engine_data(c[3]):
                line["x"] = 1                  # flagged; excluded from counts
            else:
                tally[tsv.name]["lines"] += 1
                if en:
                    tally[tsv.name]["done"] += 1
            blocks[c[0]].append(line)
            if en:
                per_block_rows[(tsv.name, c[0])].append((int(c[1], 16), en))
        files[tsv.name] = {k: v for k, v in blocks.items()}
    (OUT / "script.json").write_text(
        json.dumps(files, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    # ---- status.json ---------------------------------------------------------
    tokens = reinsert.name_token_map()
    src = reinsert.PackSource() if not (
        reinsert.IMG.exists() and reinsert.IMG.stat().st_size > 1_000_000
    ) else reinsert.IsoSource()
    budgets = {}
    for (tsv_name, block_s), rows in per_block_rows.items():
        archive = tsv_name.replace("_DAT.tsv", ".DAT").replace("_PK.tsv", ".PK")
        block_off = int(block_s, 16)
        try:
            block = src.block(archive, block_off)
            for s, e in sorted(rows, reverse=True):
                start, end = reinsert.string_span(block, s)
                block[start:end] = reinsert.compile_english(e, tokens)
            used = len(dlz.encode(bytes(block)))
            limit = src.budget(archive, block_off)
            budgets[f"{tsv_name}:{block_s}"] = {"used": used, "limit": limit}
        except Exception:
            pass
    total = sum(t["lines"] for t in tally.values())
    done = sum(t["done"] for t in tally.values())
    import patch_names
    speakers = {jp: en for jp, en in patch_names.TRANSLATIONS.items()
                if en not in ("X",)}
    token_names = {en.upper(): en for en in speakers.values()}
    # full name/term table for the Names tab (jp from the pack; en if decided)
    jp_names = reinsert.load_pack().get("jp_names", {}) if reinsert.PACK.exists() else {}
    names_table = [
        {"tok": int(t), "jp": jp,
         "en": patch_names.TRANSLATIONS.get(jp, "")}
        for t, jp in sorted(jp_names.items(), key=lambda kv: int(kv[0]))
        if jp and patch_names.TRANSLATIONS.get(jp, "") != "X"
    ]
    (OUT / "status.json").write_text(json.dumps({
        "total": total, "done": done,
        "files": dict(tally), "budgets": budgets,
        "speakers": speakers,          # ウォーリック -> Warrick (speaker column)
        "tokens": token_names,         # WARRICK -> Warrick ({NAME} display)
        "names": names_table,          # every name/term, for the Names tab
    }, ensure_ascii=False), encoding="utf-8")

    # ---- suggestions.json ----------------------------------------------------
    sugg = defaultdict(list)
    if issues_path and issues_path.exists():
        for issue in json.loads(issues_path.read_text(encoding="utf-8")):
            labels = [l["name"] for l in issue.get("labels", [])]
            if "suggestion" not in labels:
                continue
            f = parse_form(issue.get("body") or "")
            try:
                key = f["script file"] + ":" + " ".join(f["line id"].split())
            except KeyError:
                continue
            verdict = ("valid" if "valid" in labels
                       else "invalid" if "invalid" in labels else "pending")
            sugg[key].append({
                "n": issue["number"],
                "user": issue.get("user", {}).get("login", ""),
                "verdict": verdict,
                "state": issue.get("state", "open"),
            })
    (OUT / "suggestions.json").write_text(
        json.dumps(sugg, ensure_ascii=False), encoding="utf-8")

    print(f"site data: {total} lines ({done} translated), "
          f"{len(budgets)} block budgets, "
          f"{sum(len(v) for v in sugg.values())} suggestions")


if __name__ == "__main__":
    main()
