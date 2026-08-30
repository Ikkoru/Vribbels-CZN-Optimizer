"""Pinning a label column to a measured pixel width.

`width=` on a Label counts CHARACTERS, and Tk sizes a character from the
font's average -- 6px here. So a column asked for in characters is only
ever a multiple of 6, the text inside it almost never is, and the
difference is slack the label has to put somewhere. `anchor` decides
which side, and wherever that side is measured by a spacing rule, the
slack is in the gap: it has cost a set count 4px, a percent readout 2,
and a `DEF` label 4, each in a different panel.

A grid column at a measured pixel width has none. Three things have to
be true of the number, and only the first is obvious:

* it is the widest TEXT the column will hold, not the current text;
* plus `LABEL_REQUEST_INSET`, because a `minsize` is a FLOOR and the
  column still grows to its widest cell -- and a Label asks for its ink
  plus the style's own inset. A floor set to the ink alone is outgrown
  the moment the widest text appears, and the pixels come out of
  whatever shares the row;
* and the label drops its own `width=`, or it brings the slack back.

`docs/ui_spacing.md` "The rules" carries the same two traps.
"""

from tkinter import font as tkfont


# What a ttk.Label asks for beyond its ink: the style's own inset,
# measured on this theme. Half of it lands on each side, so a pinned
# column leaves the text this much short of its own edges.
LABEL_REQUEST_INSET = 4


def column_px(texts, extra=0):
    """Pixel width for a column that must hold any of `texts`.

    `extra` is added on top, for a column that wants room beyond the
    text itself -- a gap to whatever sits next to it, usually.

    Call at build time, not import: the font is not resolvable until a
    Tk root exists.
    """
    font = tkfont.nametofont("TkDefaultFont")
    widest = max((font.measure(t) for t in texts), default=0)
    return widest + LABEL_REQUEST_INSET + extra
