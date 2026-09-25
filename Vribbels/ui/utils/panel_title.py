"""The label style for a panel title built as a labelwidget.

A LabelFrame whose title shares its line with something else -- the
Optimizer's run status, a Stats list's note -- carries it as a
labelwidget, a frame of `ttk.Label`s. **A plain `TLabel` sits its text
2px in from its box on every side**, inside a 1px border and a 1px
padding, where a LabelFrame's own `text=` title has neither. So such a
title lands 2px right of every other title in its column and 2px
further from what is under it.

`panel_title_style()` gives the title's own layout, text on a fill, and
returns the style's name. Everything in the header takes it, so the
labels share one line box and the gap between them is their pad alone.
"""

from tkinter import ttk

PANEL_TITLE_STYLE = "PanelTitle.TLabel"


def panel_title_style():
    """Define the style, and return its name.

    No `try` around the layout: a refused one leaves the dotted name on
    `TLabel`'s layout, which looks exactly like no change.
    `check_tabs_build` holds these labels to their text's width.
    """
    ttk.Style().layout(PANEL_TITLE_STYLE, [("Label.fill", {
        "sticky": "nswe",
        "children": [("Label.text", {"sticky": "nswe"})]})])
    return PANEL_TITLE_STYLE
