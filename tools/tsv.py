"""Shared TSV reading for the translation surfaces.

Every script/*.tsv is a header row then tab-separated columns
(block_off, str_off, speaker, text, english). Each surface filters and keys
these differently, so this just hands back the split columns - the read,
header-skip, and split that were copy-pasted everywhere.
"""
import pathlib


def rows(path):
    """Yield the column list for each data row (header skipped, blanks skipped)."""
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines()[1:]:
        if line:
            yield line.split("\t")
