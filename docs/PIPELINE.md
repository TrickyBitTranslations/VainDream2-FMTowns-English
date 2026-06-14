# Build pipeline & translation surfaces (developer guide)

This explains how text gets from the original game into the patched English build,
the integration points in the build, and **how to add a new translation surface**.
For *writing* translations see [CONTRIBUTING.md](../CONTRIBUTING.md).

## The build in one picture

`build.ps1` (or `python tools/grow_build.py`) produces the English CD image and the
`_EN.D88` boot floppy. `grow_build.main()` runs the patchers in order, each reading
the work of the previous one:

```
patch_main_exp.main()   JP floppy -> _EN.D88 ; patch MAIN.EXP text classifier to the
                        1-byte English font + engine relocations (carved segment, etc.)
patch_names.main()      NAME.P speaker/term table -> carved segment (DATA.BIN cap escaped)
patch_items.main(write) ITEM.TOS item-name records
patch_ui.main(write)    SYSTEM.TOS / SYSTEM2.TOS / FSYS.TOS  (UI / menus / system text)
reinsert + CD build     dialogue dlz blocks -> grown CD archives (tools/patch_cd.py)
verify_patches.main()   assert the engine patches landed in the built floppy
```

Order matters: the renderer/classifier patch and the NAME.P tokens must exist before
the records that reference them are encoded.

## The translation surfaces

Each surface is independent: a place the original text lives, an extractor that lifts it
into a TSV, a translator-filled `english` column, and a re-encoder that writes it back.

| Surface | Lives in | TSV | Extractor | Re-encoder |
|---------|----------|-----|-----------|-----------|
| **Dialogue** (~4000 lines) | CD `VAIN_{A,B,C,S}.DAT` dlz blocks | `script/VAIN_*_DAT.tsv` | `export_script.py` | `reinsert.py` → `patch_cd.py` |
| **Names / terms** | `DATA.BIN` NAME.P table | `script/NAMES.tsv` | `export_names.py` | `patch_names.py` |
| **Item names** | floppy `ITEM.TOS` | (inline dict) | - | `patch_items.py` |
| **UI / system text** | floppy `SYSTEM.TOS`, `SYSTEM2.TOS`, `FSYS.TOS` | `script/SYSTEM_TOS.tsv`, `SYSTEM2_TOS.tsv`, `FSYS_TOS.tsv` | `export_ui.py` | `patch_ui.py` |

All text uses the game's custom 1-byte codec (`glodia/kana.py` for the JP source,
`glodia/english.py` for the English build). Dialogue `{Name}` tokens and the markup for
control codes are documented in CONTRIBUTING.md.

`patch_names.TRANSLATIONS` is loaded from `script/NAMES.tsv` and is the single source for
the NAME.P table, the dialogue `{Name}` token map (`reinsert.name_token_map`), and the
glossary handed to translators. Edit `NAMES.tsv` (or the `/apply` bot does via
`apply_name.py`); every consumer reads it through the `TRANSLATIONS` dict.

**Website coverage** (`tools/make_site_data.py`): the dialogue TSVs render in the main
script view; names render in the dedicated **Names tab** (built from `TRANSLATIONS`). The
site script view only ingests rows whose `block_off` is a `0x…` dlz offset, so the UI
`*_TOS.tsv` rows are committed but **not yet shown on the site** - surfacing them needs a
`make_site_data` pass + a frontend tab (a known follow-up).

## The UI text surface (worked example)

The in-game menus, status screen, equipment, battle UI, config, spell names and system
messages live in three floppy `.TOS` files in the game's raw-JIS codec (NOT the dialogue
blocks, NOT Shift-JIS). Records are `\x00`-separated and carry layout control codes.

- **`glodia/uitext.py`** - the markup codec. `decode_markup(bytes) -> str` renders a record
  for the TSV; `encode_markup(str) -> bytes` re-encodes a translation. Markup tokens:
  `\n`=newline (`0x01`), `<04>`=half-space, `<14>`=column spacer, `<03:nn>`=format op,
  `<nn>`=any other control byte, `/`=middle-dot (・), `~`=long-vowel (ー). Angle brackets
  use ASCII `< >` so the markup stays inside the 1-byte English charset.
  Round-trip is identity: `encode_markup(decode_markup(r)) == r` for every text record.
- **`export_ui.py`** - reads the three `.TOS` from the JP floppy, writes the TSVs
  (skips the file-header record and any non-text/binary records). Preserves existing
  `english` on re-export, exactly like `export_script.py`.
- **`patch_ui.py`** - reads the TSVs, re-encodes translated records, passes untranslated
  records through byte-for-byte, and writes each rebuilt file into `_EN.D88` via
  `floppy.extend_file` (the whole-file DOS loader path, same as ITEM.TOS - grows clusters
  only if the English is larger).

`reinsert.py` skips `*_TOS.tsv` (its `block_off` is a file name, not a dlz offset), so the
dialogue validator and the UI patcher don't collide.

## How to add a NEW translation surface

1. **Locate the text.** Search the files for the encoded form of a few known strings
   (`glodia.kana.encode` for the game codec; try Shift-JIS for OS-font UI). Driving the
   emulator (`tools/` Tsugaru harness) to the screen and tracing the renderer is the
   reliable way when a static search comes up empty.
2. **Write an extractor** → `script/<NAME>.tsv` with the uniform 5 columns
   `block_off  str_off  speaker  text  english`. Preserve existing `english` on re-export.
   Use a decode that round-trips (prove `encode(decode(x)) == x` on every record).
3. **Write a re-encoder/patcher** that reads the TSV, re-encodes translated rows, leaves
   the rest untouched, and writes into the build artifact (CD archive or floppy file).
4. **Wire it into `grow_build.main()`** after the patchers it depends on.
5. **Keep validators happy.** If the new TSV is not dialogue, exclude it in
   `reinsert.load_rows` (it skips `*_TOS.tsv` by suffix) and add your own `--check` if it
   needs one.
6. **Build and verify in the emulator** - confirm the strings render (not just that the
   bytes changed). Mind box geometry: English is usually longer than Japanese; the layout
   control codes (`<14>`/`<04>` spacers) assume Japanese widths, so long strings can
   overflow a menu column. Same concern as the dialogue box-width check in `reinsert.py`.
