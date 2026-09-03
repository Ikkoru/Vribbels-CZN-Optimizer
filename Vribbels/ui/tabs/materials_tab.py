"""Materials tab: three columns, one of them the growth stones.

The tab is a row of three equal columns, each headed and each holding
rows of icons with their own text. Only the rightmost has content;
the other two are placeholders at the same size, so the shape of the
tab is visible before there is anything to put in them.

A stone row's four figures are derived from THAT ROW's three counts and
no others. Premium, Great and Common are 9, 3 and 1 of the smallest
stone, so the total is the row's holdings in Common-equivalents, and
the three percentages are that total against what a full build costs at
three levels of ambition.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from pathlib import Path

from game_data import GROWTH_STONES, ATTRIBUTE_COLORS
from game_data.constants import item_art
from ..base_tab import BaseTab
from ..utils.image_utils import (
    RARITY_DIR, create_icon_with_quantity, create_placeholder_icon,
)
from ..utils.tab_header import make_heading


# The columns, left to right. Only the last has content.
COLUMN_TITLES = ("Reserved", "Reserved", "Potential Growth Stones")

# Rows are one per Element, columns one per quality, in the order the
# figures below weight them: the leftmost icon is worth the most.
ATTRIBUTES = ("Passion", "Instinct", "Void", "Order", "Justice")
QUALITIES = ("Premium", "Great", "Common")

# What each quality is worth in Common-equivalents. A Great is three
# Commons and a Premium is three Greats, so a row's total is
# 9*Premium + 3*Great + Common.
QUALITY_WEIGHTS = {"Premium": 9, "Great": 3, "Common": 1}

# The Common-equivalent cost of taking one Element's potential nodes to
# each of three levels. The rows read as increasing ambition, so each
# denominator is larger than the one above it and the same total scores
# lower against each in turn.
#
# (label, cost). The label ends in the colon the column is aligned on.
STONE_TARGETS = (
    ("Max best:", 2887),
    ("+Neutrals:", 3178),
    ("+Node 5.1 & 5.2:", 3682),
)

TOTAL_LABEL = "Total:"

# The stat lines under an Element's name. Small, because they are a
# readout under a heading rather than content in their own right.
STAT_FONT = ("Segoe UI", 9)
NAME_FONT = ("Segoe UI", 12, "bold")

# Between the icons of a row, and between one row of icons and the next.
ICON_GAP_HALF = 2       # spacing: content frame -> content frame -- frame, frame ↔
ROW_GAP = 4             # spacing: content frame -> content frame -- frame, frame ↕

# The heading of a column against the first row under it. 5 for a
# rendered 10: the row's first ink is an Element name at 12pt bold, and
# a capital starts that far down its own line box.
HEADING_GAP = 5         # spacing: panel ↕ unrelated label -- heading, frame ↕

# An Element's text block against the icons beside it, and a stat
# line's label against its value. Both are levers a rendered distance
# short of the rule, because a ttk.Label's glyphs stop inside its own
# box and these pads start at the box.
#
# The figures' block ends on a RIGHT-ALIGNED value, so what sits
# between its last digit and the icons is the label's own inset, that
# digit's right side bearing and this pad together.
TEXT_TO_ICONS = 1       # spacing: label ↔ its element -- label, frame ↔
# The four labels all end in a colon, whose ink stops inside its
# advance -- so the pad is the rule's 5 less that and the box inset.
LABEL_TO_VALUE = 2      # spacing: label ↔ its element -- label, label ↔

# How wide the figures' column is held, in digits. RESERVED rather than
# fitted: right-aligned values in a column that sizes to its content
# would move the labels beside them every time a figure gained or lost
# a digit, and each Element has its own grid, so the five blocks would
# stop lining up with each other.
#
# `100%` is the other thing the column has to hold, and a percent sign
# is wider than a digit -- so the reservation is the larger of the two
# rather than the digits alone.
VALUE_DIGITS = 4
VALUE_WIDEST = "100%"

# What a ttk.Label adds around its own text, both sides together. Its
# `minsize` is a box width and the reservation above is an ink width,
# so one has to be restated as the other. Measured at Segoe UI 9 and
# constant across every string tried.
LABEL_INSET_PX = 4

# What a figure reads before any snapshot has been loaded.
NO_DATA = "-"


class MaterialsTab(BaseTab):
    """Growth stones by Element and quality, with their totals."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.material_icons = {}     # res_id -> the Label drawing it
        self.material_stats = {}     # attribute -> {label -> value Label}
        # Kept alive by hand: a PhotoImage reaches Tk by name, and
        # nothing on the Tk side owns one, so a placeholder with no
        # Python reference is collected and the label draws empty.
        self._placeholders = []
        self.setup_ui()
        # Drawn at once with zero counts, so the tab is icons rather
        # than a wall of text before the first capture -- the images
        # are static assets and only the numbers need data.
        self._render_icons({})

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Setup the Materials tab UI."""
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        # The same pads the other headed tabs carry, because the first
        # thing under this one is the same 14pt heading they open with.
        columns.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))
        for index in range(len(COLUMN_TITLES)):
            # `uniform` is what makes the three EQUAL rather than
            # merely stretchy: without it a column holding wider
            # content takes more of the width, weights or no weights.
            columns.grid_columnconfigure(index, weight=1, uniform="materials")
        columns.grid_rowconfigure(0, weight=1)

        for index, title in enumerate(COLUMN_TITLES):
            column = ttk.Frame(columns)
            column.grid(row=0, column=index, sticky="nsew")
            self._build_column(column, title,
                               stones=index == len(COLUMN_TITLES) - 1)

    def _build_column(self, column, title, *, stones):
        """One column: a centred heading over a stack of rows.

        `stones` builds the real thing; without it the column gets the
        same shape in placeholders.
        """
        make_heading(column, title).pack(anchor=tk.CENTER)

        # `anchor=N` rather than a fill: the rows are centred on the
        # column and sit at the top of it, so the column's leftover
        # height falls below them rather than being shared out.
        rows = ttk.Frame(column)
        rows.pack(anchor=tk.N, pady=(HEADING_GAP, 0))

        for position, attribute in enumerate(ATTRIBUTES):
            row = ttk.Frame(rows)
            # Leading only, so the first row's gap upward stays the
            # heading's.
            row.pack(anchor=tk.CENTER,
                     pady=(0 if position == 0 else ROW_GAP, 0))
            self._build_row(row, attribute, stones=stones)

    def _build_row(self, row, attribute, *, stones):
        """One Element: its name and figures, then its three icons."""
        text = ttk.Frame(row)
        text.pack(side=tk.LEFT, anchor=tk.N)
        # The figures' column, held at its reserved width. `minsize` is
        # a floor, so a value wider than the reservation still widens
        # it -- which is why the reservation covers the widest form the
        # column can hold rather than four digits alone.
        text.grid_columnconfigure(1, minsize=self._value_column_px())

        name = attribute if stones else "Reserved"
        colour = (ATTRIBUTE_COLORS.get(attribute, self.colors["fg"])
                  if stones else self.colors["fg_dim"])
        # Spanning both columns with no sticky, which centres it over
        # the figures. The columns are left to size to their own
        # content: giving them weights would split the block evenly and
        # pull the colons off the value column.
        ttk.Label(text, text=name, font=NAME_FONT,
                  foreground=colour).grid(row=0, column=0, columnspan=2)

        values = {}
        for line, label in enumerate(
                (TOTAL_LABEL, *(label for label, _cost in STONE_TARGETS)),
                start=1):
            # The colons line up because the labels are right-aligned
            # in their own column and the values left-aligned in
            # theirs; the pad is the whole of the gap between them.
            ttk.Label(text, text=label, font=STAT_FONT).grid(
                row=line, column=0, sticky="e", padx=(0, LABEL_TO_VALUE))
            # `sticky=ew` with `anchor=e`: the widget fills the column
            # and the digits sit at its right. Sticking it east instead
            # would right-align the WIDGET, which is the same thing to
            # look at and leaves nothing at the column's left edge --
            # and that edge is where the label beside it is spaced from,
            # so it has to be a real one.
            value = ttk.Label(text, text=NO_DATA, font=STAT_FONT,
                              anchor=tk.E)
            value.grid(row=line, column=1, sticky="ew")
            values[label] = value
        if stones:
            self.material_stats[attribute] = values

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        for position, quality in enumerate(QUALITIES):
            label = self._make_icon_label(icons)
            # Half each side, so two neighbours sum to the rule.
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            if stones:
                res_id = self._res_id_for(attribute, quality)
                if res_id is not None:
                    self.material_icons[res_id] = label
            else:
                photo = create_placeholder_icon(
                    background=self.colors["bg_light"],
                    outline=self.colors["bg_lighter"])
                if photo is not None:
                    label.config(image=photo)
                    self._placeholders.append(photo)

    def _make_icon_label(self, parent):
        """A Label carrying nothing of its own around the icon.

        `tk.Label` defaults to a 2px border and a pixel of padding on
        each side, all of it drawn in whatever the widget's background
        is -- which is the pale edge these icons had, and which no
        change to the assets would have removed.
        """
        return tk.Label(parent, bg=self.colors["bg"], fg=self.colors["fg"],
                        bd=0, highlightthickness=0, padx=0, pady=0)

    @staticmethod
    def _value_column_px():
        """The reserved width of the figures' column, in pixels.

        Measured rather than stated: a digit's advance is the font's,
        and the column has to hold `VALUE_DIGITS` of them plus the
        Label's own inset around them.
        """
        font = tkfont.Font(font=STAT_FONT)
        widest = max(font.measure("0" * VALUE_DIGITS),
                     font.measure(VALUE_WIDEST))
        return widest + LABEL_INSET_PX

    @staticmethod
    def _res_id_for(attribute, quality):
        """The stone table's id for one Element and quality, or None."""
        for res_id, (attr, qual, _icon) in GROWTH_STONES.items():
            if attr == attribute and qual == quality:
                return res_id
        return None

    # ----------------------------------------------------------- update

    def refresh_materials(self):
        """Redraw counts and figures from the loaded snapshot.

        Called automatically after data loads.
        """
        if not self.optimizer.raw_data:
            return
        inventory = self.optimizer.raw_data.get("inventory", {})
        quantities = {}
        for item in inventory.get("items", []):
            res_id = item.get("res_id")
            if res_id:
                quantities[res_id] = item.get("amount", 0)
        self._render_icons(quantities)

    def _render_icons(self, item_quantities: dict):
        """(Re)draw every stone icon and every figure beside it.

        `item_quantities` maps res_id -> owned amount; a missing entry
        is 0, which is also how the tab looks before any snapshot is
        loaded.
        """
        images_dir = Path(__file__).parent.parent.parent / "images"
        for res_id, label in self.material_icons.items():
            if res_id not in GROWTH_STONES:
                continue
            _attribute, quality, *_rest = GROWTH_STONES[res_id]
            quantity = item_quantities.get(res_id, 0)
            # Through `item_art` rather than off the row: the tables
            # disagree about what their first fields mean and a row may
            # or may not state a rarity, so the art is read by the one
            # accessor that knows both shapes.
            art = item_art(res_id)
            icon_path = images_dir / art.icon if art else None
            plate = (images_dir / RARITY_DIR / art.plate
                     if art and art.plate else None)
            photo = (create_icon_with_quantity(
                str(icon_path), quantity, background=self.colors["bg"],
                plate_path=str(plate) if plate and plate.exists() else None)
                if icon_path and icon_path.exists() else None)
            if photo is not None:
                label.config(image=photo, text="")
                label.image = photo   # Tk holds no reference of its own
            else:
                label.config(text=f"{quality}\n{quantity}", image="")
        self._render_stats(item_quantities)

    def _render_stats(self, item_quantities: dict):
        """The four figures under each Element name.

        Every one is derived from that Element's own three counts. The
        counts are looked up per row rather than accumulated, so a row
        cannot pick up a neighbour's holdings.
        """
        for attribute, values in self.material_stats.items():
            total = 0
            for quality, weight in QUALITY_WEIGHTS.items():
                res_id = self._res_id_for(attribute, quality)
                if res_id is not None:
                    total += weight * item_quantities.get(res_id, 0)
            values[TOTAL_LABEL].config(text=str(total))
            for label, cost in STONE_TARGETS:
                values[label].config(text=f"{100 * total // cost}%")
