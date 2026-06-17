# Vain Dream II - English translation (FM Towns)

Work-in-progress English fan translation of Vain Dream II
(ヴェインドリームⅡ, Glodia, 1993, FM Towns).

This repo doesn't include the game. It's the translation plus the tooling that builds
a patched English image from your own copy.

Browse the script and suggest translations here:
<https://trickybittranslations.github.io/VainDream2-FMTowns-English/>

## Status

The engine side is "done". The `dlz` compression, text encoding, and renderer are
reverse engineered, and a handful of patched bytes in `MAIN.EXP` add a half-width
1-byte English text mode. The typewriter effect, name highlighting, and text
blips all still work.

The full script (~4,000 lines) is extracted to script/*.tsv with speaker attribution. 
A rough machine translation makes the whole game playable now, and the proper pass is underway.

## Contributing translations

See [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

- Find a line on the
  [translation site](https://trickybittranslations.github.io/VainDream2-FMTowns-English/)
  and hit Suggest. It opens a prefilled GitHub issue; a bot checks your line
  (charset, width, the scene's byte budget) and replies in about a minute.
- Or clone, edit the `english` column in `script/*.tsv`, run
  `python tools/reinsert.py --check`, and open a PR. CI validates it.

## Building the English game

Drop your game images in the repo root (names below), then:

```powershell
.\build.ps1            # CD image with current translations
.\build.ps1 -Full      # also the patched boot floppy
```

Files you supply, from your own copy:

```text
Vain DreamII (1993)(Glodia)(Jp).img   + .cue / .ccd / .sub
Vain DreamII (1993)(Glodia)(Jp)[SystemDisk].D88
```

Outputs are `Vain DreamII (1993)(Glodia)(Jp) [EN].img` (+ cue/ccd/sub) and
`...[SystemDisk]_EN.D88`. Boot both together in an FM Towns emulator like
[Tsugaru](https://github.com/captainys/TOWNSEMU).

## Credits

- Glodia & QuarterDev for the game.
- Translation and tooling by TrickyBit Translations and contributors.
- haffpizza: translations.
