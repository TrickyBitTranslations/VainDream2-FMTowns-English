# Contributing translations - Vain Dream II (FM Towns) English patch

Vain Dream II (ヴェインドリームⅡ, Glodia 1993) is an FM Towns RPG, released as
freeware by its developer (<https://www.quarter-dev.info/v2/>). The reverse
engineering is **done**: the game's compression, text encoding, and renderer
are fully mapped, the engine is patched for half-width 1-byte English, and a
build pipeline turns spreadsheet translations into a bootable disc image.

**All that's left is translating ~4,100 lines of Japanese.** That's where you
come in.

## How it works

Every dialogue line lives in `script/*.tsv` (one file per game archive):

| column | meaning |
|--------|---------|
| `block_off` | scene block (a scene = one compression unit / "budget") |
| `str_off` | string position inside the block |
| `speaker` | box title, if the line has one |
| `text` | the original Japanese (**read-only**; never edit this column) |
| `english` | **your translation goes here** (empty = stays Japanese) |

Edit the `english` column, run the checker, open a PR. The build splices your
text into the game data, re-compresses each scene, and verifies it fits.

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

`A–Z a–z 0–9 . , ! ? - ' space` plus the syntax above. Nothing else no
quotes, colons, semicolons, parentheses (no glyphs for them yet; flag it in
your PR if a line truly needs one).

### Style

- **Sentence case** ("What's for breakfast?"), not ALL CAPS. Case consistency
  also helps compression - don't mix styles within a scene.
- Use contractions; they read naturally and usually cost nothing.
- Names of people/places always via `{TOKENS}` when one exists; it keeps
  spelling consistent and renders in the highlight color.
- Keep lines ≤ ~54 characters (the checker warns); break with `\n` where it
  reads well. Match the original's box/page structure (`\p`).
- Aim for the original's meaning and tone, not word-for-word. No honorifics
  (-san/-sama); express the relationship in English instead.
- Established romanizations (see `tools/patch_names.py`): Warrick, Reina,
  Furnis, Booj, Dan, Lambert, Granny, Cecilia, Blaford, Seth, Nutts, Ride,
  Carol, Veig, Berner. Propose changes in an issue, not a PR; they're baked
  into the name table.

### Leave alone

- Rows whose Japanese contains stray `ン` mid-word or starts with `。` - those
  parses crossed event bytecode and aren't safe to replace yet.
- The `text` column, `block_off`/`str_off`, and the header row.

## The budget (why your line might get rejected)

There is **no per-line length limit**. Each scene block must *re-compress* into
its original disc footprint, so the limit is shared by all lines in the block
and depends on how repetitive the text is. Rules of thumb:

- Unique wording costs; repeated phrasing across a scene is nearly free.
- Drafting near the Japanese line's visual length usually fits.
- **The first lines into an untouched scene are the hardest.** A fully
  Japanese block packs tightly against itself, so one lone English line often
  doesn't fit even when it's short. Translating a scene wholesale (or most of
  it) works much better than single drive-by lines.. English starts matching
  English. If your line bounces on budget, consider suggesting the scene's
  neighboring lines too.
- Use the checker:

```
python tools/reinsert.py --check
  VAIN_A.DAT@0x5e8a8: 29 strings, 1296/1297 bytes (1 free)
  OVERFLOW VAIN_B.DAT@0x12345: 17 bytes over budget (8 strings) - shorten ...
```

`OVERFLOW n bytes` means trim about n characters total from *any* of that
block's translated lines (the report lists how many strings share the budget).

## Building and testing locally

Building a playable image requires your own copy of the game (free from the
developer: <https://www.quarter-dev.info/v2/>) placed in the repo root, and
Python 3.10+. From the repo root on Windows:

```powershell
.\build.ps1 -Check     # validate translations only (no game data needed)
.\build.ps1            # build the [EN] CD image from the TSVs
.\build.ps1 -Full      # also rebuild the EN boot floppy (rarely needed)
```

Boot `...[SystemDisk]_EN.D88` together with `... [EN].img` in an FM Towns
emulator (Tsugaru). Untranslated lines show as mojibake - expected: the English
build remaps the kana ranges, so only translated text and kanji render.

**You don't need the game data to contribute.** `script/blockpack.json.gz`
(committed) carries everything the checker needs, so `reinsert.py --check`
works on any clone, and CI validates every push/PR that touches `script/`.

### The easiest way to suggest a line

Open a **"Translation suggestion" issue** (Issues → New issue) - pick the
file, paste the line ID from the TSV, write your translation. A bot validates
it (syntax, width, scene budget) and comments the verdict within a minute;
maintainers apply accepted suggestions to the TSV. No fork, no PR, no setup.

## Legal

**Do not commit or redistribute the disc/floppy dumps**. PRs may only touch
`script/*.tsv` (and docs). The Japanese script text in the TSVs is reference
material for this translation effort.
