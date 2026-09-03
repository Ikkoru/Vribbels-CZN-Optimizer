"""Materials tab: three columns of upgrade material.

Combatant promotion, Partner promotion and potential growth, each a
headed column of rows and each row an item's name, its figures, and its
three tiers as icons. The leftmost icon of a row is the most valuable
one, which is what the weights below count in.

A row's figures are derived from THAT ROW's three counts and no others.
The top tier is worth nine of the bottom and the middle three, so the
total is the row's holdings in bottom-tier equivalents.

**Each column ends in a GENERIC item** -- one that stands in for the
bottom tier of any row in its column. It sits under the last row in the
rightmost icon position, beside a checkbox that adds its count to every
row's total. Off by default: the stock is shared between the rows, so
adding it to each of them counts it once per row rather than once.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from pathlib import Path

from game_data import (
    ATTRIBUTE_COLORS, COMBATANT_PROMOTION, GROWTH_STONES, PARTNER_PROMOTION,
)
from game_data.constants import item_art
from ..base_tab import BaseTab
from ..utils.checkbox import make_checkbox
from ..utils.image_utils import (
    ICON_SIZE, RARITY_DIR, create_icon_with_quantity,
)
from ..utils.tab_header import make_heading


# Where the checkbox's state is kept. NOT `combatants_show_missing`,
# which the Combatants tab's own checkbox already owns -- sharing the
# key would tie two unrelated switches together.
INCLUDE_GENERIC_KEY = "materials_include_generic"

# The six classes, in the order the game lists them. NOT the order of
# their res_id group digits, which runs Striker, Vanguard, Hunter,
# Ranger, Psionic, Controller -- Hunter and Ranger swap.
CLASS_ORDER = ("Striker", "Vanguard", "Ranger", "Hunter", "Psionic",
               "Controller")
ELEMENT_ORDER = ("Passion", "Instinct", "Void", "Order", "Justice")

# What each tier is worth in bottom-tier equivalents. Keyed by tier
# word, because the three families spell their middle tier differently.
TIER_WEIGHTS = {"Premium": 9, "Great": 3, "Advanced": 3, "Common": 1}

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

# (title, row names, the table to read, tiers left to right, the
# generic item's res_id, the figures under the total). One per column,
# left to right. The promotion columns show a total alone: nothing
# prices a full set of promotions the way the stone targets price a
# full set of nodes.
COLUMNS = (
    ("Combatant Upgrade Material", CLASS_ORDER, COMBATANT_PROMOTION,
     ("Premium", "Advanced", "Common"), 2100001, ()),
    ("Partner Upgrade Material", CLASS_ORDER, PARTNER_PROMOTION,
     ("Premium", "Advanced", "Common"), 2100002, ()),
    ("Potential Growth Stones", ELEMENT_ORDER, GROWTH_STONES,
     ("Premium", "Great", "Common"), 2100003, STONE_TARGETS),
)

# The stat lines under a row's name. Small, because they are a readout
# under a heading rather than content in their own right.
STAT_FONT = ("Segoe UI", 9)
NAME_FONT = ("Segoe UI", 12, "bold")

# Between the icons of a row, and between one row of icons and the next.
ICON_GAP_HALF = 2       # spacing: content frame -> content frame -- frame, frame ↔
ROW_GAP = 4             # spacing: content frame -> content frame -- frame, frame ↕

# The heading of a column against the first row under it, and the trim
# that goes with it. The gap runs from the heading's BASELINE to the
# row name's CAPITAL, and three things sit in it: five rows of heading
# box below the baseline, this pad, and seven rows of name box above
# the capital.
#
# The first is taken back here rather than by a bigger pad, because the
# name's seven cannot be: trimming the NAME's box would lift the whole
# figures block off the icons beside it, which are top-aligned with it.
HEADING_GAP = 3         # spacing: panel ↕ unrelated label -- heading, frame ↕
HEADING_TRIM = -5

# A row's name against the first figure under it. A lever one short of
# the rule, the name's box ending past its own baseline.
NAME_PAD_BOTTOM = -1    # spacing: label row -> label row -- label, label ↕

# A row's text block against the icons beside it, and a stat line's
# label against its value. Both are levers a rendered distance short of
# the rule, because a ttk.Label's glyphs stop inside its own box and
# these pads start at the box.
#
# The figures' block ends on a RIGHT-ALIGNED value, so what sits
# between its last digit and the icons' BOX is the label's own inset,
# that digit's right side bearing and this pad together.
#
# The icons' box and not their art: every icon carries a transparent
# border so that its art is centred the way the game centres it, and
# the border is part of the icon rather than part of the gap.
TEXT_TO_ICONS = 3       # spacing: label ↔ its element -- label, frame ↔
# The labels all end in a colon, whose ink stops inside its advance --
# so the pad is the rule's 5 less that and the box inset.
LABEL_TO_VALUE = 2      # spacing: label ↔ its element -- label, label ↔

# The generic row's checkbox against the icon beside it.
GENERIC_TO_CHECKBOX = 5  # spacing: label ↔ its element -- frame, checkbox ↔

# How wide the figures' column is held, in digits. RESERVED rather than
# fitted: right-aligned values in a column that sizes to its content
# would move the labels beside them every time a figure gained or lost
# a digit, and each row has its own grid, so the blocks would stop
# lining up with each other.
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
    """Upgrade material by class and Element, with its totals."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.material_icons = {}     # res_id -> the Label drawing it
        # (column index, row name) -> (value labels, targets, table, tiers)
        self.material_stats = {}
        self._column_generics = {}   # column index -> generic res_id
        self.include_generic_var = None
        # The last counts drawn, so the checkbox can redraw the figures
        # without a snapshot being reloaded under it.
        self._quantities = {}
        self.setup_ui()
        # Drawn at once with zero counts, so the tab is icons rather
        # than a wall of text before the first capture -- the images
        # are static assets and only the numbers need data.
        self._render_icons({})

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Setup the Materials tab UI."""
        sm = self.context.settings_manager
        self.include_generic_var = tk.BooleanVar(
            value=bool(sm.get(INCLUDE_GENERIC_KEY, False))
            if sm is not None else False)

        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        # The same pads the other headed tabs carry, because the first
        # thing under this one is the same 14pt heading they open with.
        columns.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))
        for index in range(len(COLUMNS)):
            # `uniform` is what makes the three EQUAL rather than
            # merely stretchy: without it a column holding wider
            # content takes more of the width, weights or no weights.
            columns.grid_columnconfigure(index, weight=1, uniform="materials")
        columns.grid_rowconfigure(0, weight=1)

        for index, spec in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=index, sticky="nsew")
            self._build_column(column, index, spec)

    def _build_column(self, column, index, spec):
        """One column: a centred heading, its rows, then its generic."""
        title, names, table, tiers, generic, targets = spec
        make_heading(column, title,
                     bottom_trim=HEADING_TRIM).pack(anchor=tk.CENTER)

        # `anchor=N` rather than a fill: the rows are centred on the
        # column and sit at the top of it, so the column's leftover
        # height falls below them rather than being shared out.
        rows = ttk.Frame(column)
        rows.pack(anchor=tk.N, pady=(HEADING_GAP, 0))

        for position, name in enumerate(names):
            row = ttk.Frame(rows)
            # Leading only, so the first row's gap upward stays the
            # heading's.
            row.pack(anchor=tk.CENTER,
                     pady=(0 if position == 0 else ROW_GAP, 0))
            self._build_row(row, index, name, table, tiers, targets)

        self._column_generics[index] = generic
        generic_row = ttk.Frame(rows)
        generic_row.pack(anchor=tk.CENTER, pady=(ROW_GAP, 0))
        self._build_generic_row(generic_row, generic, len(tiers))

    def _build_row(self, row, index, name, table, tiers, targets):
        """One class or Element: its name and figures, then its icons."""
        text = ttk.Frame(row)
        text.pack(side=tk.LEFT, anchor=tk.N)
        # The figures' column, held at its reserved width. `minsize` is
        # a floor, so a value wider than the reservation still widens
        # it -- which is why the reservation covers the widest form the
        # column can hold rather than four digits alone.
        text.grid_columnconfigure(1, minsize=self._value_column_px())

        # Spanning both columns with no sticky, which centres it over
        # the figures. The columns are left to size to their own
        # content: giving them weights would split the block evenly and
        # pull the colons off the value column.
        ttk.Label(text, text=name, font=NAME_FONT,
                  foreground=ATTRIBUTE_COLORS.get(name, self.colors["fg"]),
                  padding=(0, 0, 0, NAME_PAD_BOTTOM),
                  ).grid(row=0, column=0, columnspan=2)

        values = {}
        for line, label in enumerate(
                (TOTAL_LABEL, *(word for word, _cost in targets)), start=1):
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
        self.material_stats[(index, name)] = (values, targets, table, tiers)

        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N, padx=(TEXT_TO_ICONS, 0))
        for position, tier in enumerate(tiers):
            label = self._make_icon_label(icons)
            # Half each side, so two neighbours sum to the rule.
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            res_id = self._res_id_for(table, name, tier)
            if res_id is not None:
                self.material_icons[res_id] = label

    def _build_generic_row(self, row, res_id, tier_count):
        """The column's stand-in item, under its last row.

        Placed in the LAST icon column, under the tier it substitutes
        for, with the checkbox beside it. The columns before it are
        held open by empty frames of an icon's width, so the icon lands
        under the bottom tier rather than at the row's left edge.
        """
        icons = ttk.Frame(row)
        icons.pack(side=tk.LEFT, anchor=tk.N)
        for position in range(tier_count):
            if position < tier_count - 1:
                ttk.Frame(icons, width=ICON_SIZE[0], height=1).grid(
                    row=0, column=position, padx=ICON_GAP_HALF)
                continue
            label = self._make_icon_label(icons)
            label.grid(row=0, column=position, padx=ICON_GAP_HALF)
            self.material_icons[res_id] = label

        # spacing: label ↔ its element -- frame, checkbox ↔
        make_checkbox(
            row, self.colors, text="Add to totals",
            variable=self.include_generic_var,
            command=self._on_include_generic_toggle,
        ).pack(side=tk.LEFT, anchor=tk.N, padx=(GENERIC_TO_CHECKBOX, 0))

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
    def _res_id_for(table, group, tier):
        """A table's id for one group and tier, or None."""
        for res_id, row in table.items():
            if row[0] == group and row[1] == tier:
                return res_id
        return None

    # ----------------------------------------------------------- update

    def _on_include_generic_toggle(self):
        """Remember the checkbox and redraw the figures under it."""
        sm = self.context.settings_manager
        if sm is not None:
            sm.set(INCLUDE_GENERIC_KEY, bool(self.include_generic_var.get()))
        self._render_stats(self._quantities)

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
        # The three generic items are CURRENCIES, which a snapshot
        # keeps apart from its item list -- so a column's stand-in
        # reads 0 from `items` alone however many are held.
        currencies = (self.optimizer.raw_data.get("characters")
                      or {}).get("currencies") or {}
        for key, record in currencies.items():
            try:
                quantities[int(key)] = record.get("amount", 0)
            except (TypeError, ValueError):
                continue
        self._render_icons(quantities)

    def _render_icons(self, item_quantities: dict):
        """(Re)draw every icon and every figure beside it.

        `item_quantities` maps res_id -> owned amount; a missing entry
        is 0, which is also how the tab looks before any snapshot is
        loaded.
        """
        self._quantities = item_quantities
        images_dir = Path(__file__).parent.parent.parent / "images"
        for res_id, label in self.material_icons.items():
            quantity = item_quantities.get(res_id, 0)
            # Through `item_art` rather than off a table row: the
            # tables disagree about what their first fields mean and a
            # row may or may not state a rarity, so the art is read by
            # the one accessor that knows every shape.
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
                label.config(text=str(quantity), image="")
        self._render_stats(item_quantities)

    def _render_stats(self, item_quantities: dict):
        """The figures under each row's name.

        Every one is derived from that row's own counts. The counts are
        looked up per row rather than accumulated, so a row cannot pick
        up a neighbour's holdings.

        The generic item is the exception, and only when the checkbox
        asks for it: its stock is shared across the column, so adding
        it to each row counts it once per row rather than once. That is
        what the checkbox is for and why it is off by default.
        """
        include = bool(self.include_generic_var
                       and self.include_generic_var.get())
        for (index, name), (values, targets, table, tiers) in \
                self.material_stats.items():
            total = 0
            for tier in tiers:
                res_id = self._res_id_for(table, name, tier)
                if res_id is not None:
                    total += (TIER_WEIGHTS.get(tier, 1)
                              * item_quantities.get(res_id, 0))
            if include:
                generic = self._column_generics.get(index)
                if generic is not None:
                    total += item_quantities.get(generic, 0)
            values[TOTAL_LABEL].config(text=str(total))
            for label, cost in targets:
                values[label].config(text=f"{100 * total // cost}%")
