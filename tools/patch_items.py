"""Translate ITEM.TOS (ITEM.P) item names to English.

ITEM.TOS records are item names built from three kinds of span:
  - literal text   : 1-byte custom katakana (0xac+, ー=0x1e, の=0x87) and/or
                     2-byte raw JIS kanji (both bytes 0x21..0x7e)
  - ⟨02 nn⟩ insert : pulls NAME.P record nn (1-based) — base words like Sword,
                     Armor, Mail, Robe, Ring, Boots, Rod (translated by patch_names.py)
  - grade/format   : Ｍ/Ｓ grade prefixes (JIS), control bytes 0x03 nn / 0x14 / 0x1a..

Only the *literal* spans are stored in ITEM.TOS and were never translated, so a
compound like レザー⟨02 Armor⟩ renders "<mojibake>Armor". We translate the literal
spans in place (glodia/english.py, 1-byte ASCII — needs the patch_main_exp.py
classifier patch) and keep tokens/grades verbatim.

The lookup (MAIN.EXP @0x3c55 → carved-seg variant) counts NUL separators, so record
LENGTHS are free; only the record COUNT must stay fixed. ITEM.TOS is read at its true
file size (DOS 3F, count=0xffffffff) into the 32 KB carved segment, so it can grow far
past the original 1217 B — bounded by the floppy's free space, not RAM.

Usage:  python tools/patch_main_exp.py && python tools/patch_names.py && \
        python tools/patch_items.py [--write]
        (no --write = dry run: report budget + before/after, touch nothing)
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from glodia import kana
from glodia.english import encode as een, decode as edec
from extract_floppy import read_file


def decode_jis(pair):
    """2-byte raw JIS X 0208 -> kanji char: OR each byte with 0x80 -> EUC-JP
    (phase-D). `pair` is exactly the two text bytes (both 0x21..0x7e)."""
    return bytes(b | 0x80 for b in pair).decode("euc-jp")

EN_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"

# --- literal Japanese run -> English. Genitive の is rendered "'s "/" " inline,
#     so suffix runs like "の杖" carry the connector. Runs left out of this map
#     are kept as original bytes (still mojibake) and reported as TODO. ---
TRANS = {
    # grade prefixes (JIS Ｍ/Ｓ before a base name)
    "Ｍ": "M.", "Ｓ": "S.",
    # --- swords / blades (katakana) ---
    "ダガー": "Dagger", "レイピア": "Rapier", "エストック": "Estoc", "シミター": "Scimitar",
    "ブロード": "Broad", "バスタード": "Bastard", "グレート": "Great",
    # --- swords / blades (kanji) ---
    "飛燕剣": "Swallow Blade", "雷神剣": "Thunder Blade", "飛鳥剣": "Falcon Blade",
    "岩斬中華包丁": "Cleaver", "の剣": "'s Sword", "の長剣": "'s Longsword",
    "の大剣": "'s Greatsword",
    # --- axes / polearms ---
    "ハンド": "Hand", "バトル": "Battle", "岩清水の斧": "Springwater Axe",
    "遊爆大鉄槌": "War Maul", "ハルバード": "Halberd", "の斧槍": "'s Halberd",
    "モール": "Maul", "スピア": "Spear", "トライデント": "Trident", "パイク": "Pike",
    "スカルスマッシュ": "Skull Smash", "フレイル": "Flail", "メイス": "Mace",
    "モーニングスター": "Morning Star", "ピック": "Pick", "ウォーハンマー": "War Hammer",
    # --- staves / rods ---
    "の杖": "'s Staff", "賢者の杖": "Sage's Staff", "銀の杖": "Silver Staff",
    "カーズの杖": "Curse Staff", "炎の": "Flame ",
    # --- bows / thrown ---
    "スリング": "Sling", "ダート": "Dart", "セルフボウ": "Self Bow", "ロングボウ": "Longbow",
    "コンポジットボウ": "Composite Bow", "クロスボウ": "Crossbow", "深海の弓": "Abyss Bow",
    # --- shields ---
    "バックラー": "Buckler", "ラウンドシールド": "Round Shield", "ヒーターシールド": "Heater Shield",
    "カイトシールド": "Kite Shield", "タワーシールド": "Tower Shield", "重盾": "Heavy Shield",
    "の盾": "'s Shield",
    # --- body armor ---
    "レザー": "Leather", "ハードレザー": "Hard Leather", "リング": "Ring", "スケイル": "Scale",
    "ラメラー": "Lamellar", "チェイン": "Chain", "ブレスト": "Breast", "プレート": "Plate",
    "フレイム": "Flame", "ショルダーガード": "Shoulder Guard", "暗黒装甲": "Dark Plate",
    "重装甲": "Heavy Plate", "朱雀の鎧": "Suzaku Armor", "碧雲の鎧": "Azure Armor",
    "の鎧": "'s Armor",
    # --- robes / cloaks ---
    "フィールド": "Field", "エンブレスコート": "Emblace Coat", "エレメンタルガード": "Elemental Guard",
    "賢者の": "Sage's", "カーズの": "Curse ", "黒の": "Black ", "冥界の": "Abyss ",
    "クワールの": "Quall's",
    # --- rings ---
    "ラピスの": "Lapis ", "ルーンの": "Rune ", "銀の": "Silver ", "金の": "Gold ",
    "白銀の": "Platinum ", "紅玉の": "Ruby ", "結婚": "Wedding", "大地の": "Earth ",
    "太陽の": "Sun ",
    # --- boots / feet ---
    "レザーシューズ": "Leather Shoes", "プロテクト": "Protect", "エレメンタル": "Elemental",
    "スライディング": "Sliding", "下駄": "Geta", "女王様のハイヒール": "Queen's Heels",
    "装甲靴": "Armored Boots",
    # --- consumables / misc / key items ---
    "ヒール": "Heal", "極楽キノコ": "Bliss Mushroom", "ハリマンの風車": "Hariman Windmill",
    "鶏の餌": "Chicken Feed", "飴玉": "Candy", "煎餅": "Cracker", "ライフブースター": "Life Booster",
    "ヒールストック": "Heal Stock", "のペンダント": "'s Pendant", "紫": "Purple ",
    "カルの手紙": "Cal's Letter", "の手紙": "'s Letter", "迷宮の鍵": "Maze Key",
    "の鍵": "'s Key", "鎧の紋章": "Armor Crest", "大鍋": "Cauldron", "白銀の鍵": "Platinum Key",
    "銀のプレート": "Silver Plate", "金のプレート": "Gold Plate", "銅のプレート": "Copper Plate",
    "銅の": "Copper ", "砂漠のバラ": "Desert Rose", "ピロム": "Pirom",
    # genitive particle when standing alone between two tokens (Mage の Robe)
    "の": "'s ",
}


def segment(r, nrecs):
    """[(kind, value)] where kind in {'lit','tok','ctrl'}; 'lit' value is JP text,
    'tok'/'ctrl' value is the raw bytes to preserve verbatim."""
    def is_jis(b):
        return 0x21 <= b <= 0x7e
    segs, cur, i = [], [], 0
    def flush():
        if cur:
            segs.append(["lit", "".join(cur)]); cur.clear()
    while i < len(r):
        b = r[i]
        if b == 0x02 and i + 1 < len(r):
            flush(); segs.append(["tok", r[i:i + 2]]); i += 2; continue
        if b == 0x03 and i + 1 < len(r):
            flush(); segs.append(["ctrl", r[i:i + 2]]); i += 2; continue
        if b in (0x14, 0x1a, 0x1b, 0x1f):
            flush(); segs.append(["ctrl", bytes([b])]); i += 1; continue
        if b == 0x87:
            cur.append("の"); i += 1; continue
        if b == 0x1e:
            cur.append("ー"); i += 1; continue
        if b >= 0xac:
            try:
                cur.append(kana.decode(bytes([b])))
            except Exception:
                flush(); segs.append(["ctrl", bytes([b])])
            i += 1; continue
        if is_jis(b) and i + 1 < len(r) and is_jis(r[i + 1]):
            cur.append(decode_jis(r[i:i + 2])); i += 2; continue
        flush(); segs.append(["ctrl", bytes([b])]); i += 1
    flush()
    return segs


def tok_en(raw, nrecs):
    """English of a ⟨02 nn⟩ insert (for the before/after preview only)."""
    nn = raw[1]; idx = nn - 1
    return "{" + (edec(nrecs[idx]) if 0 <= idx < len(nrecs) else f"?{nn:#x}") + "}"


SPACE = een(" ")   # ⟨04⟩


def reencode(r, nrecs, todo):
    """Rebuild a record with literal spans translated; tokens/ctrl preserved.

    Inserts a space between an adjacent literal and ⟨02⟩ token (either order) so
    compounds read "Broad Sword" / "Mage's Staff", not "BroadSword". A connector
    that already supplies its own spacing (leading/trailing space or "'s") suppresses
    the inserted space."""
    pieces = []   # (kind, bytes, preview_text)
    for kind, val in segment(r, nrecs):
        if kind == "lit":
            if val in TRANS:
                en = TRANS[val]; pieces.append(("lit", een(en), en))
            else:
                todo.add(val); pieces.append(("lit", _raw_of(val, r), f"«{val}»"))
        elif kind == "tok":
            pieces.append(("tok", val, tok_en(val, nrecs)))
        else:
            pieces.append(("ctrl", val, ""))

    def is_word(p):   # a rendered word: a token, or a non-empty literal
        return p[0] == "tok" or (p[0] == "lit" and bool(p[2]))
    out = bytearray(); preview = []
    for i, piece in enumerate(pieces):
        kind, b, txt = piece
        if i and is_word(pieces[i - 1]) and is_word(piece):
            left, right = pieces[i - 1][2], txt
            clean = left.endswith(" ") or right.startswith((" ", "'"))
            if not clean:
                out += SPACE; preview.append(" ")
        out += b; preview.append(txt)
    return bytes(out), "".join(preview)


def _raw_of(text, r):
    """Best-effort: return the original bytes for an untranslated literal run by
    re-segmenting (kept verbatim so untranslated items are unchanged, not corrupted)."""
    # Re-walk r and collect the byte span whose decoded text == this run.
    # Simplible: rebuild per-char source is complex; instead caller passes whole r,
    # and we locate by decoding incrementally.
    return _slice_for_run(r, text)


def _slice_for_run(r, text):
    def is_jis(b):
        return 0x21 <= b <= 0x7e
    i = 0; spans = []; cur = []; start = 0
    def dec_here():
        return "".join(cur)
    while i < len(r):
        b = r[i]
        if b == 0x02 and i + 1 < len(r):
            if cur and dec_here() == text:
                return bytes(r[start:i])
            cur = []; i += 2; start = i; continue
        if b == 0x03 and i + 1 < len(r):
            if cur and dec_here() == text:
                return bytes(r[start:i])
            cur = []; i += 2; start = i; continue
        if b in (0x14, 0x1a, 0x1b, 0x1f):
            if cur and dec_here() == text:
                return bytes(r[start:i])
            cur = []; i += 1; start = i; continue
        if not cur:
            start = i
        if b == 0x87:
            cur.append("の"); i += 1
        elif b == 0x1e:
            cur.append("ー"); i += 1
        elif b >= 0xac:
            try:
                cur.append(kana.decode(bytes([b])))
            except Exception:
                cur = []
            i += 1
        elif is_jis(b) and i + 1 < len(r) and is_jis(r[i + 1]):
            cur.append(decode_jis(r[i:i + 2])); i += 2
        else:
            cur = []; i += 1
        if cur and dec_here() == text:
            return bytes(r[start:i])
    return b""


def main(write=None):
    if write is None:                      # CLI use: dry run unless --write
        write = "--write" in sys.argv
    fs = read_d88(EN_D88.read_bytes())
    item = read_file(fs, "ITEM.TOS")
    nrecs = read_file(fs, "DATA.BIN")[4123 + 8:].split(b"\x00")
    assert item[:8] == b"ITEM.P\x01.", item[:8]
    header, body = item[:8], item[8:]
    recs = body.split(b"\x00")

    todo = set()
    new_recs, rows = [], []
    for idx, r in enumerate(recs):
        if not r:
            new_recs.append(r); continue
        nb, preview = reencode(r, nrecs, todo)
        new_recs.append(nb)
        rows.append((idx, r, nb, preview))

    new_item = header + b"\x00".join(new_recs)
    cap = fs.file_capacity("ITEM.TOS")
    print(f"ITEM.TOS: {len(recs)} records  |  {len(item)} -> {len(new_item)} bytes "
          f"(cluster cap {cap}; loader reads true file size into 32 KB carved seg)")
    fits = "FITS in current clusters" if len(new_item) <= cap else \
           f"NEEDS FAT12 grow (+{len(new_item) - cap} B)"
    print(f"  budget: {fits}")
    print(f"  translated runs: {len(TRANS)}  |  untranslated literal runs (TODO): {len(todo)}\n")
    for idx, r, nb, preview in rows:
        print(f"{idx:3d} | {preview}")
    if todo:
        print(f"\n=== {len(todo)} literal runs still untranslated (kept as-is) ===")
        for t in sorted(todo):
            print(f"   «{t}»")
    if write:
        # grow_file rewrites in place within ITEM.TOS's existing cluster and updates
        # the dir size; raises if we ever exceed the 2048 B allocation.
        img = fs.grow_file("ITEM.TOS", new_item)
        EN_D88.write_bytes(img)
        print(f"\nwrote ITEM.TOS ({len(new_item)} B) -> {EN_D88.name}")
    else:
        print("\n(dry run — pass --write to apply)")


if __name__ == "__main__":
    main()
