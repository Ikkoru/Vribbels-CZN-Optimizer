"""One All/None button row for the whole UI.

Four panels grew their own -- Slots, Sets, Main Stats and the
Optimizer's Exclude Combatant's MFs -- and no two agreed on all three
of the row's numbers. The row gap split two against two, so there was
not even a majority to be wrong about, which is the point: these were
copied and nudged, never decided.

The numbers here are LEVERS. What they render is measured, per panel,
because the panels' own paddings differ and the same lever produces a
different inset in each -- see `ui/spacing_registry.py`.
"""

import tkinter as tk
from tkinter import ttk

# Between the checkbox block above and this row.
ROW_GAP = 2

# The leading pad on `All`, feeding its distance from the panel's border.
EDGE_PAD = 2

# Half the gap between the two buttons: each spends this on the side
# facing the other, so the pair sums to twice it.
HALF_BUTTON_GAP = 2

# Both buttons take the same width so the pair reads as one control
# rather than two of different sizes.
BUTTON_WIDTH = 5


def make_all_none_row(parent, on_all, on_none, *, width=BUTTON_WIDTH):
    """Build a panel's All/None row, pack it, and return it.

    Args:
        parent: the panel the row belongs to.
        on_all: called when All is pressed.
        on_none: called when None is pressed.
        width: button width in characters. Only pass one to make the
            pair wider than the labels need; narrower clips them.

    Returns:
        The row, already packed.
    """
    row = ttk.Frame(parent)
    # spacing: checkbox block -> All/None row -- checkbox, button ↕
    row.pack(fill=tk.X, pady=(ROW_GAP, 0))

    # spacing: border edge -> button -- panel, button ↔
    # spacing: button -> button -- button, button ↔
    ttk.Button(row, text="All", width=width, command=on_all).pack(
        side=tk.LEFT, padx=(EDGE_PAD, HALF_BUTTON_GAP))
    ttk.Button(row, text="None", width=width, command=on_none).pack(
        side=tk.LEFT, padx=(HALF_BUTTON_GAP, 0))
    return row
