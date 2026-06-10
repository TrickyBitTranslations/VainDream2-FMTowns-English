# Vain Dream II - English translation (FM Towns)

Work-in-progress English fan translation of **Vain Dream II**
(ヴェインドリームⅡ, Glodia, 1993, FM Towns).

The game was released by one of its developers - you can get it from
[quarter-dev.info](https://www.quarter-dev.info/v2/). This repo does **not**
contain the game; it contains the translation and the tooling that builds a
patched, bootable English image from your own copy.

**Browse the script and suggest translations here:**
**<https://trickybittranslations.github.io/VainDream2-FMTowns-English/>**

## Status

- Engine work done: the game's `dlz` compression, custom text encoding, and
  renderer are fully reverse engineered. A few patched bytes in `MAIN.EXP`
  give the game a half-width 1-byte English text mode (with the original
  typewriter effect, name highlighting, and text blips intact).
- The full script, **~4,000 lines**, is extracted to `script/*.tsv` with
  speaker attribution.
- The opening scenes are translated and playable. Everything else needs
  translating: that's the part you can help with.

## Contributing translations

See **[CONTRIBUTING.md](CONTRIBUTING.md)**. Short version:

- Easiest: find a line on the
  [translation site](https://trickybittranslations.github.io/VainDream2-FMTowns-English/)
  and hit **Suggest** - it opens a prefilled GitHub issue. A bot checks your
  line (charset, width, the scene's byte budget) and replies in about a
  minute. No setup needed at all.
- Or clone, edit the `english` column in `script/*.tsv`, run
  `python tools/reinsert.py --check`, and open a PR. Validation runs in CI.

Translating doesn't require the game or any dependencies beyond Python 3.10+
- the repo carries the data the validator needs (`script/blockpack.json.gz`).

## Building the English game

Put your game images in the repo root (names below), then:

```powershell
.\build.ps1            # CD image with current translations
.\build.ps1 -Full      # also the patched boot floppy
```

Expected files (from your own copy of the game):

```text
Vain DreamII (1993)(Glodia)(Jp).img   + .cue / .ccd / .sub
Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88
```

Outputs: `Vain DreamII (1993)(Glodia)(Jp) [EN].img` (+ cue/ccd/sub) and
`...[SystemDisk]_EN.D88`. Boot both together in an FM Towns emulator
(e.g. [Tsugaru](https://github.com/captainys/TOWNSEMU)). Untranslated lines
show as garbled text in the English build; that's expected and goes away as
the script gets translated.

## Credits

- **Glodia / Quarter Dev** - the game, and for releasing it free.
- Translation & tooling - TrickyBit Translations and contributors.
