"""One tab header for the whole UI: a 14pt heading with its subtitle
beside it on the same line.

Three tabs hand-rolled this and their corrections had drifted -- five
values, and no two tabs agreed on three of them. The numbers were never
independently arrived at; they were copied and then nudged, which is
what makes them a helper's job rather than three call sites'.

**The paddings correct the FONT, not the layout.** A 14pt Label renders
its text about 5px in from its own top edge where a LabelFrame title
renders flush, so identical container padding puts a heading several
pixels lower than the panel titles beneath it. The negative components
cancel that; `docs/ui_spacing.md` "The rules" is canonical.

The subtitle sits on the heading's line rather than under it, which is
what `anchor=tk.S` buys -- bottom-aligned, so the two baselines meet
despite the size difference.
"""

import tkinter as tk
from tkinter import ttk

HEADING_FONT = ("Segoe UI", 14, "bold")

# The heading's own box, trimmed to its ink. Top clears the blank
# leading above the capitals, bottom the space below the descenders.
HEADING_PAD_TOP = -3
HEADING_PAD_BOTTOM = -2

# The subtitle is 9pt and sits bottom-aligned, so its bottom padding is
# what places its ink: `anchor=tk.S` pins the box's bottom edge, and
# taking padding off that edge pulls the ink DOWN with it. 0, not a
# negative -- at -4 all three subtitles read 4px low.
SUBTITLE_PAD_BOTTOM = 0

# Leading pad on the subtitle. NOT the rule's 14: the heading's box ends
# past its ink and the subtitle's begins before its own, and the two
# together spend 4px that no padding here can see. Measured at 18 when
# this was 14.
SUBTITLE_PAD_LEFT = 10


def make_tab_header(parent, colors, title, subtitle, *, x_trim=0):
    """Build a tab's header row, pack it, and return it.

    Args:
        parent: the containing widget.
        colors: the app palette; the subtitle takes `fg_dim` from it.
        title: the 14pt heading's text.
        subtitle: the 9pt line beside it.
        x_trim: NEGATIVE pixels off the heading's leading edge, for a tab
            whose header sits one container deeper than the rest. Not a
            style choice -- accumulated container padding genuinely
            starts such a tab's heading further right, and this is what
            brings it back level with the others. Every tab at the usual
            depth passes nothing.

    Returns:
        The header row, already packed. Returned so a caller can measure
        it or add to it, not because anything currently does.
    """
    row = ttk.Frame(parent)
    # spacing: content frame -> content frame -- frame, frame ↕
    row.pack(fill=tk.X, pady=(0, 2))

    # spacing: header subtext -- heading, label ↔
    ttk.Label(
        row, text=title, font=HEADING_FONT,
        padding=(x_trim, HEADING_PAD_TOP, 0, HEADING_PAD_BOTTOM),
    ).pack(side=tk.LEFT, anchor=tk.S)

    # spacing: heading ↔ element -- heading, label ↔
    ttk.Label(
        row, text=subtitle, foreground=colors["fg_dim"],
        padding=(0, 0, 0, SUBTITLE_PAD_BOTTOM),
    ).pack(side=tk.LEFT, anchor=tk.S, padx=(SUBTITLE_PAD_LEFT, 0))

    return row
