# Markup codes in the script

The `english` column isn't plain text. A handful of codes carry over from the
original game and it needs them, so don't strip them out!

## Names

`{WARRICK}`, `{REINA}`, etc insert a character's name in the highlight
color. They're case-insensitive, and `python tools/reinsert.py --tokens` prints
the full list. Always use these (when they exist) instead of typing a name out, 
so the spelling stays consistent and the color is right.

One catch: if a line already shows the speaker as the red title at the top of the
box, don't start the body with the name again or it shows up twice.

## Line and page breaks

`\n` is a line break inside the same box.

`\p` is a page break. The game waits for a button press, clears the box, and
opens a fresh one. Use it for long passages instead of cramming everything into
one box.

## Layout codes

`<14>` is a column spacer, basically a tab. It jumps to the next column so things
line up, mostly in menus and place names like `Inn<14>Ryukotei`. Leave it where
it is or the columns collapse. You can put English on either side of it.

`<04>` is a half-width space the Japanese text used for spacing between glyphs.
You can usually just drop it in English.

`<03:nn>` is a formatting op (color, text speed, that kind of thing) with one
argument. Copy it through unchanged. A bare `<nn>` is some other control byte,
same deal, leave it alone.

## Punctuation

`...` turns into the game's own ellipsis (・・・). Just type three dots.

`'` gives you a real apostrophe, so use contractions freely.

`・` is the bullet for choice menus. Keep one per choice line, like the original.

In the UI text (the `.TOS` files) you'll also run into `/` for the middle dot and
`~` for the long-vowel mark. Leave those as-is too.

## What you can actually type

Letters, numbers, and `. , ! ? - ' space`, plus the codes above. No quotes,
colons, semicolons, or parentheses yet, since there are no glyphs for them. If a
line genuinely needs one, flag it in your PR or suggestion.
