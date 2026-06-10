"""Translate NAME.P records (names/terms used by ⟨02 nn⟩ inserts + speaker titles).

The engine lookup (MAIN.EXP @0x42b6) scans NUL separators, so record LENGTHS are
free as long as (a) the record count/order is unchanged and (b) the total byte
length of the rewritten span stays exact (binary data follows the table inside
DATA.BIN). Shortfall is absorbed by shrinking the 未使用 ("unused") placeholder
records and padding the last one with ⟨04⟩.

Operates on the classifier-patched floppy IN PLACE (run patch_main_exp.py first):
translations are 1-byte ASCII (glodia/english.py) and need that patch to render.

Usage: python tools/patch_main_exp.py && python tools/patch_names.py
"""
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from glodia.floppy import read_d88
from glodia.script import _decode_record
from glodia.english import encode as en

EN_D88 = ROOT / "Vain DreamII (1993)(Glodia)(Jp)[SystemDisk]_EN.D88"
TABLE_OFF = 4123 + 8       # NAME.P body inside DATA.BIN (after "NAME.P" header)

# keyd by ORIGINAL decoded text - provisional romanizations, adjust freely
# (sentence case; {NAME} lookups in reinsert.py are case-insensitive)
TRANSLATIONS = {
    "ウォーリック": "Warrick",
    "レイナ": "Reina",
    "ファーニス": "Furnis",
    "ライド": "Ride",
    "セシリア": "Cecilia",
    "ブラフォード": "Blaford",
    "セス": "Seth",
    "ブージ": "Booj",
    "ナッツ": "Nutts",
    "大婆様": "Gran",
    "ダ　ン": "Dan",
    "ランバート": "Lambert",
    "キャロル": "Carol",
    "ベイグ": "Veig",
    "バーナー王子": "Berner",
    "いらっしゃい": "Welcome",
    "へへっ": "Haha",
    "お兄ちゃん": "Bro",
    "の武器屋": "Weapon Shop",
    # role / title tokens — used as highlighted box-title prefixes before a
    # literal given name (e.g. {Swordmaiden} Sherry); highlight carries to \n.
    # (the name table is tight on space; more await the DATA.BIN budget fix)
    "女剣士": "Swordmaiden",
    "剣士": "Swordsman",
    "看護兵": "Medic",
    "ドラゴン　ライダー": "Dragon Rider",
    "を受け取った。": "received",
    # the table now grows freely (FAT12 grow) — romanize away. Provisional:
    "重装騎兵団": "Hvy Cavalry",
    "重装騎兵": "Cavalry",
    "聖騎士団": "Paladins",
    "聖騎士": "Paladin",
    "騎士団": "Knights",
    "ブレイス": "Brace",
    "グリーク": "Greek",
    "パーシャ": "Pasha",
    "エリオット": "Eliot",
    "ゼロ船長": "Capt Zero",
    "ポップ": "Pop",
    "タップ": "Tap",
    "ウィルディース艦長": "Capt Wildeath",
    "シンシア": "Cynthia",
    "カル伯爵": "Count Cal",
    "クレイボーン": "Claybourne",
    "マージス": "Margis",
    "シュタイナー": "Steiner",
    "竜騎士": "Dragon Knight",
    "の宿屋": "Inn",
    "の道具屋": "Item Shop",
    "の防具屋": "Armor Shop",
    "の魔法屋": "Magic Shop",
    # --- characters / monsters ---
    "ドリアード": "Dryad", "ドード": "Dode", "ビアガン": "Biagan", "バーグ": "Berg",
    "カーム": "Calm", "ナイトメア": "Nightmare", "パチュンガ": "Pachunga",
    "ライランド": "Ryland", "クーレイア": "Kuleia", "アスタルト": "Astarte",
    "メーフィス": "Mephis", "フロスト": "Frost", "パディッシュ": "Paddish",
    "バーダル": "Bardal", "カーネル": "Karnel", "ブレイ": "Brei", "フォーゲル": "Vogel",
    "ルード": "Rude", "ダイン": "Dyne", "ピローム": "Pirom", "ダイガーン": "Daigarn",
    "モビーディック": "Moby Dick", "ウィルディース": "Wildeath", "ゼロ": "Zero",
    "ローラ": "Laura", "クラウス": "Klaus", "ソウルン": "Souln", "アトォム": "Atom",
    "パンツァードラグーン": "Panzer Dragoon", "ローラ ": "Laura",
    # --- places ---
    "クラウスの村": "Klaus Village", "氷の洞窟": "Ice Cavern", "レジーナの森": "Regina Forest",
    "ジーク王国": "Zeke Kingdom", "ジーク城": "Zeke Castle", "ジーク": "Zeke",
    "カナール採掘場": "Canal Mine", "マーズトンネル": "Mars Tunnel", "マーズ砦": "Mars Fort",
    "メインキャンプ": "Main Camp", "セルーシュ王国": "Serush Kingdom",
    "セルーシュ城": "Serush Castle", "セルーシュ": "Serush", "地下礼拝堂": "Catacombs",
    "地下水道": "Sewers", "神殿遺跡": "Temple Ruins", "紫水晶の丘": "Amethyst Hill",
    "シルバーホーン": "Silverhorn", "砂の城": "Sand Castle", "砂の海": "Sand Sea",
    "石の王国": "Stone Kingdom", "ドワーフの洞窟": "Dwarf Cave", "マージスの洞窟": "Margis Cave",
    "フローディーテの森": "Frodite Forest", "鎧の塔": "Armor Tower", "地下宮殿": "Crypt",
    "タリアトフ大陸": "Taliatov", "バッカス２世号": "Bacchus II", "クイーンストーカー号": "Queen Stalker",
    # --- roles / titles / monsters ---
    "守護騎士": "Guardian", "神官竜": "Priest Dragon", "神竜": "Divine Dragon", "魔神": "Demon God",
    "魔導士": "Mage", "ドワーフ": "Dwarf", "デーモン": "Demon", "ハンター": "Hunter",
    "魔物": "Monster", "宮廷魔術師": "High Mage", "大神官": "High Priest", "ワイバーン": "Wyvern",
    "水晶竜": "Crystal Dragon", "神官戦士": "Monk", "騎士達": "Knights",
    "ダークエルフ": "Dark Elf", "ミノタウロス": "Minotaur", "精霊達": "Spirits", "砂鯨": "Sand Whale",
    "船長": "Capt", "キメラ": "Chimera", "砂船": "Sand Ship", "潜砂艦": "Sand Sub", "海賊": "Pirate",
    "エルフ": "Elf", "騎士": "Knight", "メデューサ": "Medusa", "リッチ": "Lich", "ドラグーン": "Dragoon",
    "マスター": "Master", "精霊": "Spirit", "亡霊": "Ghost", "八賢者": "Eight Sages", "見張り": "Guard",
    "団長": "Cmdr", "金竜": "Gold Dragon", "銀竜": "Slvr Dragon", "白竜": "Wht Dragon",
    "緑竜": "Grn Dragon", "黒竜": "Blk Dragon", "炎竜": "Fire Dragon", "水竜": "Wer Dragon",
    "水晶の角": "Crystal Horn", "パラサイト　デーモン": "Parasite Demon", "女の子": "Girl",
    # --- items / magic ---
    "黄金のナイフ": "Gold Knife", "ポーション": "Potion", "天の水晶": "Sky Crystal",
    "地の水晶": "Earth Crystal", "ブーツ": "Boots", "ミスリル": "Mythril", "ジオクリスタル": "Geo Crystal",
    "指輪": "Ring", "ロッド": "Rod", "薬草袋": "Herb Pouch", "薬草": "Herb", "ナイフ": "Knife",
    "ローブ": "Robe", "マント": "Cloak", "ライトニング　ボルト": "Lightning Bolt", "テミス": "Themis",
    "暗黒魔術": "Dark Magic", "魔導弾": "Magic Bolt", "遠見の水晶": "Scrying Crystal",
    "アーマー": "Armor", "メイル": "Mail", "ソード": "Sword", "アックス": "Axe", "金属製": "Metal",
    "紫水晶": "Amethyst", "水晶": "Crystal", "ショップ": "Shop", "換金": "Exchange",
    "３剣７": "Sword", "３鎧７": "Armor", "３斧７": "Axe", "３槍７": "Spear", "３盾７": "Shield",
    # --- common phrases / UI fragments / suffixes ---
    "おじさん": "Mister", "おばさん": "Lady", "あんちゃん": "Bud", "おじちゃん": "Mister",
    "が仲間に加わった。": " joined party.", "が仲間から外れた。": " left party.",
    "やめる": "Cancel", "・品物を見せて。": "・Show your wares.", "・話をしよう。": "・Let's talk.",
    "・持物を売ります。": "・Sell items.", "・テミスを換金して。": "・Exchange Themis.",
    "・瞬間移動したい。": "・Teleport.", "・お店を出よう。": "・Leave shop.",
    "ありがとうございました": "Thank you.", "ありがとう": "Thanks", "じゃ。": "Well then.",
    "キャンプ": "Camp", "宝箱": "Chest", "魔法陣": "Magic Circle",
    "・・・・・": ".....", "・・・": "...",
    "ォォォォォォォ": "Aaah", "ぇぇぇぇぇぇぇ": "Eeeh",
    "天の法皇よ": "O God.", "地の法皇よ。": "O Titan.",
    "魔導の法たる我に力を与えたまえ。": "Magic, grant me power.",
    "魔の根源たるその炎で、我が敵を焼きつくせ。": "With flame at, burn my foes to ash.",
    # left untranslated: grammar particles (ますか/です。/んです。/ですか？ — inserted
    # mid-sentence, don't map to English standalone), ∪, and the binary tail record.
    "未使用": "X",          # placeholder records, left untranslated
}
PAD_RECORD = "未使用"       # last placeholder absorbs the remaining slack


def read_file_from(fs, name):
    from extract_floppy import read_file
    return read_file(fs, name)


def main():
    fs = read_d88(EN_D88.read_bytes())
    data_bin = read_file_from(fs, "DATA.BIN")

    # The whole region from TABLE_OFF to EOF is ONE NUL-separated table; the
    # engine looks records up by counting NULs (position-independent), so record
    # LENGTHS are free. BUT DATA.BIN is read by absolute disk sector — it can't
    # move or gain a cluster — so the table must fit DATA.BIN's capacity. If the
    # full set overflows, drop the costliest (biggest English-over-Japanese)
    # translations until it fits.
    recs = data_bin[TABLE_OFF:].split(b"\x00")
    decoded = [_decode_record(r) for r in recs]
    # DATA.BIN can't move (read by absolute sector), but the game reads its full
    # 6-sector cluster allocation (6144B) regardless of the directory size, so the
    # table may use all of it — not just the original 6085 bytes.
    cap = fs.file_capacity("DATA.BIN")
    chosen = {i for i, d in enumerate(decoded) if d in TRANSLATIONS and d != PAD_RECORD}
    pad_idx = max(i for i, d in enumerate(decoded) if d == PAD_RECORD)

    def body(sel, pad=0):
        # empty ALL unused placeholder records (reclaims their bytes); translate
        # chosen; keep the rest. The pad record then absorbs the exact slack.
        out = [en(TRANSLATIONS[decoded[i]]) if i in sel
               else (b"" if decoded[i] == PAD_RECORD else r)
               for i, r in enumerate(recs)]
        out[pad_idx] = b"\x04" * pad
        return data_bin[:TABLE_OFF] + b"\x00".join(out)

    dropped = []
    while len(body(chosen)) > cap and chosen:
        worst = max(chosen, key=lambda i: len(en(TRANSLATIONS[decoded[i]])) - len(recs[i]))
        chosen.discard(worst)
        dropped.append(decoded[worst])
    # pad the placeholder so DATA.BIN is exactly its original size
    new_data_bin = body(chosen, cap - len(body(chosen)))
    assert len(new_data_bin) == cap
    img = fs.grow_file("DATA.BIN", new_data_bin)
    EN_D88.write_bytes(img)

    fs2 = read_d88(EN_D88.read_bytes())
    from glodia.english import decode as en_dec
    check = read_file_from(fs2, "DATA.BIN")[TABLE_OFF:].split(b"\x00")
    print(f"name table: {len(chosen)} of {len(chosen)+len(dropped)} names translated "
          f"(DATA.BIN held at {cap} bytes — read by absolute sector, can't grow)")
    if dropped:
        print(f"  {len(dropped)} didn't fit (kept Japanese): {', '.join(dropped[:14])}"
              + (" ..." if len(dropped) > 14 else ""))
    for i in sorted(chosen)[:5]:
        print(f"  token {i+1:#04x}: {decoded[i]!r} -> {en_dec(check[i])!r}")


if __name__ == "__main__":
    main()
