# Contributing translations - Vain Dream II (FM Towns)

Two ways to help, both fine:

- **Web UI, no setup.** Open the
  [translation site](https://trickybittranslations.github.io/VainDream2-FMTowns-English/),
  find a line, and hit **Suggest**. It opens a GitHub issue with the file and line
  already filled in; you just type the English. A bot checks it (charset, line
  width, scene budget) and comments back in about a minute, and maintainers apply
  the good ones. No fork, no clone.
- **Pull request.** Edit the `english` column in `script/*.tsv`, run the checker,
  open a PR. CI validates it.

## How it works

Every dialogue line lives in `script/*.tsv` (one file per game archive):

| column | meaning |
|--------|---------|
| `block_off` | scene block (a scene = one compression unit / "budget") |
| `str_off` | string position inside the block |
| `speaker` | box title, if the line has one |
| `text` | the original Japanese. Read-only, never edit this column |
| `english` | your translation (empty = stays Japanese) |

Edit the `english` column, run the checker, open a PR. The build splices your
text into the game data, re-compresses each scene, and checks it fits.

UI and menu strings (`SYSTEM_TOS.tsv`, `SYSTEM2_TOS.tsv`, `FSYS_TOS.tsv`) work
the same way. These are the menus, status screen, battle UI, spell names, and
system messages. Their `text` carries layout control codes you should copy into
your `english`:

| token | meaning |
|-------|---------|
| `\n` | new menu row |
| `<14>` | column spacer (keep these between menu items so the layout holds) |
| `<04>` | half-space (Japanese inter-glyph spacing; usually drop it in English) |
| `<03:nn>` | a format op, copy it through unchanged |
| `/` | middle dot ・ (e.g. `Weapon/Item`) |
| `~` | long-vowel mark ー |

Keep these short, they go in fixed-width boxes (see Length below).

## Writing translations

### Syntax

| you write | the game shows |
|-----------|----------------|
| `\n` | line break inside the box |
| `\p` | page break (wait for button, clear box) - use where the original has an embedded `スピーカー名\n` mid-line, followed by `{NAME}\n` |
| `{WARRICK}`, `{REINA}`, … | the character's name, in highlight color (case-insensitive; run `python tools/reinsert.py --tokens` for the full list) |
| `...` | the game's ・・・ ellipsis |
| `'` | a proper apostrophe (don't avoid contractions!) |
| `・` | choice-menu bullet (keep one per choice line, as in the original) |

### Character set

`A-Z a-z 0-9 . , ! ? - ' space` plus the syntax above. Nothing else, no quotes,
colons, semicolons, or parentheses (there are no glyphs for them yet). If a line
really needs one, flag it in your PR.

### Style

- Sentence case ("What's for breakfast?"), not ALL CAPS. Mixing case within a
  scene also hurts compression.
- Use contractions. They read naturally and usually cost nothing.
- Use `{TOKENS}` for people and place names whenever one exists. It keeps
  spelling consistent and renders in the highlight color.
- Keep lines around 37 characters or less (the checker warns), and break with
  `\n` where it reads well. Match the original's box and page structure (`\p`).
- Go for the original's meaning and tone, not word-for-word. No honorifics
  (-san/-sama); put the relationship into the English instead.
- Established romanizations live in `script/NAMES.tsv` (also `reinsert.py
  --tokens`): Warrick, Reina, Furnis, Booj, Dan, Lambert, Granny, Cecilia,
  Blaford, Seth, Nutts, Ride, Carol, Veig, Berner. To change one, open an issue
  rather than a PR; they're baked into the name table.

### Leave alone

- Rows whose Japanese has a stray `ン` mid-word or starts with `。`. Those parses
  crossed into event bytecode and aren't safe to replace yet.
- The `text` column, `block_off`/`str_off`, and the header row.

## Length: no byte budget, but mind the box

There's no length budget. The build grows the game's data and repoints the engine
to match, so a line can be as long as it needs. (Scenes used to have a fixed
compressed-size budget, but that's gone now.)

The real limit is visual. A dialogue box is about 37 half-width characters wide
and a few lines tall. Anything past the width gets clipped or wraps mid-word. So:

- Break lines with `\n` so each stays under ~37 cells.
- Split a long passage across boxes with `\p` rather than overflowing one.
- The checker warns when a rendered line is too wide:

```text
python tools/reinsert.py --check
  VAIN_A.DAT@0x5e8a8: 29 strings, 1402 bytes (was 1297)
  WARN VAIN_B_DAT.tsv:120: rendered line 2 is 44 cells (max ~37) - will be cut off or wrapped mid-word
```

## Building and testing locally

You don't need the game to translate. `script/blockpack.json.gz` (committed) has
everything the checker needs, so `reinsert.py --check` runs on any clone, and CI
validates every push or PR that touches `script/`.

To build a playable image you need your own copy of the game in the repo root,
plus Python 3.10+. From the repo root on Windows:

```powershell
.\build.ps1 -Check     # validate translations only (no game data needed)
.\build.ps1            # build the EN boot floppy + CD image from the TSVs
```

Boot `...[SystemDisk]_EN.D88` with `... [EN].img` in an FM Towns emulator
(Tsugaru). Untranslated lines show as mojibake; the English build remaps the kana
ranges, so only translated text and kanji render.

## Legal

Don't commit or redistribute the disc or floppy dumps. PRs may only touch
`script/*.tsv` and docs. The Japanese script text in the TSVs is reference
material for the translation.
