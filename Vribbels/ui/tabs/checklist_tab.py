"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it. **Labels only so far** -- nothing here reads a
snapshot yet. What it is waiting for is completion status, and the
capture already carries the first pieces of that: `point_entity` for
the daily and weekly activity totals, `mission_entities` for a
per-mission `complete_time`, and `season_pass_entity` for the
Arkhianon Supply's rank. See `docs/capture_pipeline.md`.

The columns are built the way the Materials tab's are: content in the
EVEN grid columns with an empty expanding one between each pair, so the
block spans the window and the gaps across it stay equal. A row is one
Text per column rather than a Label per line -- a tab switch re-runs
the geometry managers over every widget on the page, and forty labels
is forty of them.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from ..base_tab import BaseTab
from ..utils.tab_header import make_heading
from ui.scaling import px


# Each column's heading and its rows, left to right. Read off the
# game: the wording is the game's own where it has one, and `$hop`
# marks a shop tab rather than a currency.
#
# **A column's rows are its own.** `Arkhianon Supply` appears under
# three headings because it resets three ways -- a daily set of
# missions, a weekly set, and the pass itself -- and they are three
# different things to check rather than one row repeated.
COLUMNS = (
    ("Daily", (
        "Coffee",
        "Activity (Dailies)",
        "Arkhianon Supply",
        "Dates",
        "Delegation",
        "Other Events",
    )),
    ("Weekly", (
        "Nono's Shop",
        "$hop - Memory Archive - Traveler",
        "Arkhianon Supply",
        "Simulation Challenges",
        "Chaos & Sortie Currency",
        "Seasonal Event(s)",
        "Seasonal Shop",
        "Seasonal Accumulated Score",
    )),
    ("Monthly", (
        "Nono's Shop",
        "$hop - Memory Archive - Traveler",
        "$hop - Zeronium Shop",
        "$hop - Blackhorn Trade",
        "$hop - Exchange Shop - Prism Module",
    )),
    ("Other", (
        "Basin of Hyperspace (21 days)",
        "Zero System Chaos Matrix (84? days)",
        "Arkhianon Supply (42? days)",
        "Seasonal Event (21 + 21 + 21 days)",
        "Sortie (21 days)",
        "Other Events",
    )),
)

# The rows' face. The headings use the shared helper's own.
ROW_FONT = ("Segoe UI", 9)

# What separates one row from the next, as `spacing1` on every line
# after the first. A lever a rendered distance short of the rule: a
# Text line's own box already carries part of the pitch, and unlike a
# padding this cannot go negative.
ROW_PITCH = 4           # spacing: label row -> label row -- run, run ↕

# The heading of a column against the first row under it. The gap runs
# from the heading's BASELINE to the row's CAPITAL, with the heading's
# box below its baseline and the row's box above its capital both
# inside it -- which is why the lever is at its floor.
HEADING_GAP = 0         # spacing: panel ↕ unrelated label -- heading, frame ↕

# What a Text puts around its own content, both sides together. Its
# `width` is in CHARACTERS and this block is sized in pixels, so the
# holder is fixed and the Text fills it.
TEXT_INSET = 2


class ChecklistTab(BaseTab):
    """The recurring-task columns."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.setup_ui()

    def setup_ui(self):
        """Build the Checklist tab UI."""
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((0, 2)))

        # Content in the EVEN grid columns, an empty expanding one
        # between each pair. Given to spacers of one uniform group the
        # leftover width lands as equal gaps with the block flush
        # against both edges; shared out inside the content cells it
        # lands unequally, the widest column keeping the least.
        for index in range(len(COLUMNS) + 1):
            columns.grid_columnconfigure(2 * index, weight=0)
        for index in range(len(COLUMNS)):
            # spacing: content frame -> content frame -- frame, frame ↔
            # NOT TRACKED: the distance is whatever the tab has spare
            # divided four ways, so it moves with the window. What is
            # fixed is that the four are equal.
            columns.grid_columnconfigure(2 * index + 1, weight=1,
                                         uniform="checklist")
        columns.grid_rowconfigure(0, weight=1)

        self.column_texts = {}
        for index, (title, rows) in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=2 * index, sticky="nsew")
            self._build_column(column, title, rows)

    def _build_column(self, parent, title, rows):
        """One heading and the rows under it."""
        make_heading(parent, title).pack(anchor=tk.CENTER)

        font = tkfont.Font(font=ROW_FONT)
        width = max(font.measure(row) for row in rows) + TEXT_INSET
        holder = tk.Frame(parent, width=width,
                          height=self._block_height(len(rows)),
                          bg=self.colors["bg"])
        holder.pack_propagate(False)
        # spacing: panel ↕ unrelated label -- heading, frame ↕
        holder.pack(anchor=tk.N, pady=px((HEADING_GAP, 0)))

        text = tk.Text(
            holder, wrap=tk.NONE, bd=0, highlightthickness=px(0),
            padx=px(0), pady=px(0),
            bg=self.colors["bg"], fg=self.colors["fg"], font=ROW_FONT,
            # Selectable but never focusable, and no insertion cursor:
            # the rows can be copied, and nothing about them invites
            # typing.
            takefocus=0, insertwidth=px(0), cursor="arrow",
        )
        text.pack(fill=tk.BOTH, expand=True)
        # spacing: label row -> label row -- run, run ↕
        text.tag_configure("row", spacing1=px(ROW_PITCH))
        text.insert("1.0", "\n".join(rows), "row")
        text.config(state=tk.DISABLED)
        self.column_texts[title] = text

    @staticmethod
    def _block_height(rows):
        """A column's height: its rows and the pitch between them.

        Measured off the face rather than multiplied by a guess -- a
        Text sizes in LINES and this block is pinned in pixels, so the
        two have to be reconciled somewhere.
        """
        return (rows * tkfont.Font(font=ROW_FONT).metrics("linespace")
                + (rows - 1) * px(ROW_PITCH))
